# -*- mode: ruby -*-
# vi: set ft=ruby :
#
# Automation Alchemy - Vagrantfile
#
# Vagrant has ONE job: create the VMs (CPU, RAM, network, hostname) and give
# each one a 'devops' user that Ansible can log into. Everything else
# (updates, hardening, firewall, Docker, app, Jenkins) is done by Ansible.
#
# Flow of a single `vagrant up`:
#   1. Generate an SSH key pair in keys/ (first run only)
#   2. Boot every VM except cicd-server
#      -> bootstrap.sh creates 'devops' and installs the public key
#   3. Boot cicd-server LAST
#      -> bootstrap.sh also installs Ansible + the private key
#      -> Ansible runs site.yml and configures ALL VMs
#
# Bonus VMs (bonus: true in the inventory) are only created with:
#   PowerShell:  $env:ENABLE_BONUS="true"; vagrant up

require "yaml"

ROOT         = File.dirname(File.expand_path(__FILE__))
INVENTORY    = File.join(ROOT, "ansible", "inventory", "hosts.yml")
KEY_DIR      = File.join(ROOT, "keys")
KEY_PATH     = File.join(KEY_DIR, "ansible_key")
IMAGE        = "ubuntu/jammy64"
ENABLE_BONUS = ENV["ENABLE_BONUS"] == "true"

# ---------------------------------------------------------------------------
# 1. SSH key pair for Ansible (and for you, as the devops user).
#    Generated once, never committed (keys/ is in .gitignore).
# ---------------------------------------------------------------------------
unless File.exist?(KEY_PATH)
  Dir.mkdir(KEY_DIR) unless Dir.exist?(KEY_DIR)
  ok = system("ssh-keygen", "-t", "ed25519", "-N", "", "-q",
              "-C", "ansible@automation-alchemy", "-f", KEY_PATH)
  abort "Could not generate SSH key with ssh-keygen. Is OpenSSH Client installed?" unless ok
end

# Ansible needs the vault password to decrypt secrets (devops password, ...).
# Checked before creating any VM, but only for commands that provision.
VAULT_PASS = File.join(ROOT, ".vault_pass")
if (ARGV & ["up", "provision"]).any? && !File.exist?(VAULT_PASS)
  abort ".vault_pass not found in #{ROOT}. Create it first (see README)."
end

# ---------------------------------------------------------------------------
# 2. Read the VM list from the Ansible inventory (single source of truth).
#    The inventory is a tree (all -> core -> webservers -> web-server-1),
#    so we walk it recursively and collect every host with its group name.
# ---------------------------------------------------------------------------
def collect_hosts(group, data, nodes)
  (data["hosts"] || {}).each do |name, vars|
    nodes << { name: name, group: group, ip: vars["ansible_host"],
               memory: vars["vm_memory"], cpus: vars["vm_cpus"],
               bonus: vars["bonus"] == true }
  end
  (data["children"] || {}).each do |child, child_data|
    collect_hosts(child, child_data || {}, nodes)
  end
end

all_nodes = []
collect_hosts("all", YAML.load_file(INVENTORY)["all"], all_nodes)

# Skip bonus VMs unless ENABLE_BONUS=true, then move cicd-server to the end.
nodes = all_nodes.reject { |n| n[:bonus] && !ENABLE_BONUS }
NODES = nodes.reject { |n| n[:group] == "cicd" } + nodes.select { |n| n[:group] == "cicd" }

# Tell Ansible whether bonus VMs exist (so it never tries to reach a missing VM).
ANSIBLE_EXTRA = ENABLE_BONUS ? "-e enable_bonus=true" : ""

# Create VMs one at a time - parallel boots fight over CPU/disk (P2 lesson).
ENV["VAGRANT_NO_PARALLEL"] = "1"

Vagrant.configure("2") do |config|
  config.vm.box          = IMAGE
  config.vm.boot_timeout = 1800 # cloud-init can be slow on first boot

  NODES.each do |node|
    config.vm.define node[:name] do |vm|
      vm.vm.hostname = node[:name]
      vm.vm.network "private_network", ip: node[:ip]

      # Only the load balancer is exposed to the host (browser -> localhost:8080).
      if node[:group] == "loadbalancers"
        vm.vm.network "forwarded_port", guest: 80, host: 8080
      end

      # Only cicd-server needs the project files (to run Ansible).
      # Every other VM gets NO shared folder - less attack surface.
      if node[:group] != "cicd"
        vm.vm.synced_folder ".", "/vagrant", disabled: true
      end

      vm.vm.provider "virtualbox" do |vb|
        vb.name         = "alchemy-#{node[:name]}"
        vb.memory       = node[:memory]
        vb.cpus         = node[:cpus]
        vb.linked_clone = true # clone from one base disk: faster + less disk space
      end

      # Every VM: devops user + public key
      vm.vm.provision "file", source: "#{KEY_PATH}.pub", destination: "/tmp/ansible_key.pub"
      vm.vm.provision "shell", path: "vagrant/bootstrap.sh", args: [node[:group]]

      # cicd-server only: run Ansible against the whole infrastructure
      if node[:group] == "cicd"
        vm.vm.provision "shell", name: "ansible-site", privileged: false, inline: <<-SHELL
          set -e
          sudo -u devops -H bash -c 'cd ~/automation-alchemy/ansible && ANSIBLE_FORCE_COLOR=1 ansible-playbook site.yml #{ANSIBLE_EXTRA}'
        SHELL
      end
    end
  end
end
