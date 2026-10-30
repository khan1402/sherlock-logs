// Jenkinsfile - Automation Alchemy CI/CD pipeline.
//
// Jenkins checks Gitea every minute. For every new commit:
//   1. Version      - the short commit ID becomes the image tag (e.g. 3f2a1bc),
//                     and the version users see right now is recorded (for rollback)
//   2. Code checks  - lint (Ruff), code security (Bandit), unit tests (pytest)
//   3. Build        - build the backend and frontend images
//   4. Image scan   - Trivy: stop if an image has a CRITICAL fixable vulnerability
//   5. Push         - push to Docker Hub + save build-info.txt as the build artifact
//   6. Deploy       - Ansible deploys the new tag: backend, then web servers one at a time
//   7. Smoke test   - check through the load balancer that the new version is live
//   8. Load test    - k6: 5 users for 20 s, fail on errors or slow pages
//
// If anything fails AFTER the deploy started (6-8), the previous version is
// deployed again automatically. Every result is posted to Slack (#deployments).

pipeline {
    agent any

    options {
        timestamps()
        ansiColor('xterm')
        disableConcurrentBuilds()                       // never two deploys at once
        buildDiscarder(logRotator(numToKeepStr: '20'))  // keep the last 20 builds
        timeout(time: 30, unit: 'MINUTES')
    }

    environment {
        // Must match dockerhub_user in ansible/group_vars/all/vars.yml
        DOCKERHUB_USER      = 'zeek14'
        LB_URL              = 'http://192.168.56.10/'
        ANSIBLE_FORCE_COLOR = '1'
        // Tool images (run as throwaway containers - nothing installed on the CI server).
        // 'latest' keeps the vulnerability scanner current; pin versions in production.
        TRIVY_IMAGE         = 'aquasec/trivy:latest'
        K6_IMAGE            = 'grafana/k6:latest'
    }

    stages {
        stage('Version') {
            steps {
                script {
                    // Every image traces back to exactly one commit.
                    env.IMAGE_TAG = sh(script: 'git rev-parse --short=7 HEAD', returnStdout: true).trim()
                    currentBuild.displayName = "#${env.BUILD_NUMBER} ${env.IMAGE_TAG}"
                    // What users see right now = what we roll back to if this deploy fails.
                    env.PREVIOUS_TAG = sh(script: 'bash ci/live-version.sh "$LB_URL"', returnStdout: true).trim()
                }
                sh 'git log -1 --format="Commit %h by %an: %s"'
                echo "Live version before this build: ${env.PREVIOUS_TAG ?: 'none (site not reachable)'}"
            }
        }

        stage('Code checks') {
            steps {
                sh 'rm -rf reports'
                sh 'bash ci/code-checks.sh backend'
                sh 'bash ci/code-checks.sh frontend'
            }
        }

        stage('Build images') {
            steps {
                sh '''
                    for component in backend frontend; do
                      docker build \
                        --build-arg APP_VERSION="$IMAGE_TAG" \
                        --tag "$DOCKERHUB_USER/alchemy-$component:$IMAGE_TAG" \
                        "app/$component"
                    done
                '''
            }
        }

        stage('Image scan') {
            steps {
                // Trivy runs as a throwaway container. Its vulnerability database is
                // kept in the 'trivy-cache' Docker volume, so only the first scan downloads it.
                sh '''
                    trivy() {
                      docker run --rm \
                        --volume /var/run/docker.sock:/var/run/docker.sock \
                        --volume trivy-cache:/root/.cache \
                        "$TRIVY_IMAGE" image --quiet --scanners vuln --ignore-unfixed "$@"
                    }
                    for component in backend frontend; do
                      image="$DOCKERHUB_USER/alchemy-$component:$IMAGE_TAG"
                      echo "=== Trivy: $image - HIGH + CRITICAL (report only) ==="
                      trivy --severity HIGH,CRITICAL --exit-code 0 "$image"
                      echo "=== Trivy: $image - gate: fail on CRITICAL with a fix available ==="
                      trivy --severity CRITICAL --exit-code 1 "$image"
                    done
                '''
            }
        }

        stage('Push to Docker Hub') {
            steps {
                // Jenkins hides these values in the log (shown as ****).
                withCredentials([usernamePassword(credentialsId: 'dockerhub',
                                                  usernameVariable: 'DH_USER',
                                                  passwordVariable: 'DH_TOKEN')]) {
                    sh '''
                        echo "$DH_TOKEN" | docker login --username "$DH_USER" --password-stdin
                        # Retry: one dropped connection to Docker Hub must not fail the build.
                        # A push is safe to repeat - layers already uploaded are skipped.
                        for component in backend frontend; do
                          image="$DOCKERHUB_USER/alchemy-$component:$IMAGE_TAG"
                          for attempt in 1 2 3; do
                            docker push "$image" && break
                            if [ "$attempt" -eq 3 ]; then
                              echo "Push of $image failed 3 times" >&2
                              exit 1
                            fi
                            echo "Push of $image failed (attempt $attempt of 3), retrying in 15 s..."
                            sleep 15
                          done
                        done
                    '''
                }
                // The build artifact: which commit produced which exact images.
                sh '''
                    {
                      echo "version:  $IMAGE_TAG"
                      echo "commit:   $(git rev-parse HEAD)"
                      echo "built:    $(date -u +%Y-%m-%dT%H:%M:%SZ)"
                      echo "jenkins:  build #$BUILD_NUMBER"
                      for component in backend frontend; do
                        echo "$component: $(docker image inspect --format '{{index .RepoDigests 0}}' "$DOCKERHUB_USER/alchemy-$component:$IMAGE_TAG")"
                      done
                    } > build-info.txt
                    cat build-info.txt
                '''
                archiveArtifacts artifacts: 'build-info.txt', fingerprint: true
            }
        }

        stage('Deploy') {
            steps {
                script {
                    // From here on, a failure means the servers may run a broken
                    // version -> the post section rolls back.
                    env.DEPLOY_STARTED = 'true'
                    deployVersion(env.IMAGE_TAG)
                }
            }
        }

        stage('Smoke test') {
            steps {
                sh 'bash scripts/smoke-test.sh "$LB_URL" "$IMAGE_TAG"'
            }
        }

        stage('Load test') {
            steps {
                sh '''
                    docker run --rm -i \
                      --env TARGET_URL="$LB_URL" \
                      --env VERSION="$IMAGE_TAG" \
                      "$K6_IMAGE" run --quiet - < ci/load-test.js
                '''
            }
        }
    }

    post {
        always {
            // Unit test results -> "Tests" tab and trend graph in Jenkins.
            junit testResults: 'reports/*.xml', allowEmptyResults: true
        }
        success {
            notifySlack('SUCCESS', "Version ${env.IMAGE_TAG} is live on http://localhost:8080")
        }
        failure {
            script {
                if (env.DEPLOY_STARTED != 'true') {
                    // Failed in a quality gate or build step: production was never touched.
                    notifySlack('BLOCKED', "Version ${env.IMAGE_TAG} failed before deploy. " +
                                      "Users still see ${env.PREVIOUS_TAG ?: 'the previous version'}.")
                } else if (!env.PREVIOUS_TAG) {
                    notifySlack('ROLLBACK_FAILED', "Version ${env.IMAGE_TAG} failed after deploy and " +
                                              "there is no known previous version to roll back to.")
                } else {
                    echo "=== ROLLBACK: deploying the previous version ${env.PREVIOUS_TAG} ==="
                    try {
                        deployVersion(env.PREVIOUS_TAG)
                        sh 'bash scripts/smoke-test.sh "$LB_URL" "$PREVIOUS_TAG"'
                        notifySlack('ROLLED_BACK', "Version ${env.IMAGE_TAG} failed after deploy. " +
                                              "Rolled back to ${env.PREVIOUS_TAG} - users see a working site.")
                    } catch (err) {
                        notifySlack('ROLLBACK_FAILED', "Version ${env.IMAGE_TAG} failed AND the rollback to " +
                                                  "${env.PREVIOUS_TAG} failed: ${err.getMessage()}")
                    }
                }
            }
        }
        cleanup {
            // Don't leave Docker Hub login details on the CI server.
            sh 'docker logout || true'
            // Remove leftover image layers so the disk doesn't fill up over time.
            sh 'docker image prune -f'
        }
    }
}

// --- Helpers ---------------------------------------------------------------

// Deploy one version with the same deploy.yml as the very first deploy.
def deployVersion(String tag) {
    withCredentials([
        sshUserPrivateKey(credentialsId: 'ansible-ssh-key', keyFileVariable: 'SSH_KEY'),
        file(credentialsId: 'ansible-vault-pass', variable: 'VAULT_PASS_FILE')
    ]) {
        withEnv(["DEPLOY_TAG=${tag}"]) {
            sh '''
                export ANSIBLE_PRIVATE_KEY_FILE="$SSH_KEY"
                export ANSIBLE_VAULT_PASSWORD_FILE="$VAULT_PASS_FILE"
                cd ansible
                ansible-playbook deploy.yml -e image_tag="$DEPLOY_TAG"
            '''
        }
    }
}

// Post the result to Slack. A missing credential or a Slack outage never fails the build.
def notifySlack(String status, String text) {
    try {
        withCredentials([string(credentialsId: 'slack-webhook', variable: 'SLACK_WEBHOOK_URL')]) {
            withEnv(["NOTIFY_STATUS=${status}", "NOTIFY_TEXT=${text}"]) {
                sh 'bash ci/notify.sh'
            }
        }
    } catch (err) {
        echo "Slack notification skipped: ${err.getMessage()}"
    }
}
