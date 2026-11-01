#!/usr/bin/env bash
# es-yellow.sh - review test: "Elasticsearch cluster status changes to yellow or red".
#
#   bash scripts/demo/es-yellow.sh          stop node es02 -> cluster turns YELLOW
#   bash scripts/demo/es-yellow.sh restore  start es02 again -> back to GREEN
#
# Every index has one replica copy, kept on the other node. Without es02 the
# replicas have nowhere to live: all data is still there (on es01), but not
# twice - that is exactly what yellow means.
# Expected: "Elasticsearch cluster yellow or red" after about 1 minute.

# The scripts below in single quotes run ON the VM, so their $variables must
# NOT expand here on the laptop - single quotes are intended (SC2016).
# shellcheck disable=SC2016
# shellcheck source=/dev/null  # _common.sh sits next to this script
source "$(dirname "$0")/_common.sh"

ACTION="${1:-stop}"
require_vm "$MON_VM"

if [[ "$ACTION" == "restore" ]]; then
  on_vm "$MON_VM" '
    sudo docker start es02 >/dev/null && echo "es02 started - waiting for green (up to 2 min)..."
    for _ in $(seq 1 24); do
      status=$(curl -s localhost:9200/_cluster/health | grep -o "\"status\":\"[a-z]*\"" | cut -d\" -f4)
      [[ "$status" == "green" ]] && break
      sleep 5
    done
    echo "Cluster status: ${status:-unknown}"
  '
  exit 0
fi

on_vm "$MON_VM" '
  sudo docker stop es02 >/dev/null && echo "es02 stopped"
  sleep 5
  echo "Cluster health now:"
  curl -s "localhost:9200/_cluster/health?pretty" | grep -E "\"(status|number_of_nodes|unassigned_shards)\""
'
echo "Expected: 'Elasticsearch cluster yellow or red' after ~1 min. Restore: bash scripts/demo/es-yellow.sh restore"
where_to_look
