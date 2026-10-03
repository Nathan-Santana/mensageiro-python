#!/usr/bin/env bash
# Envia uma mensagem para app1 e confere se chegou em app1, app2 e app3.
set -u
MSG="teste-$(date +%s)"
FAIL=0

echo "== Aguardando as instâncias =="
for port in 5001 5002 5003; do
  for _ in $(seq 1 30); do
    curl -sf "http://localhost:$port/messages" > /dev/null && break
    sleep 1
  done
done

echo "== POST /send em app1 (5001) =="
curl -s -X POST -H "Content-Type: application/json" \
  -d "{\"message\":\"$MSG\"}" http://localhost:5001/send
echo -e "\n"

echo "== GET /messages em cada instância =="
for port in 5001 5002 5003; do
  if curl -s "http://localhost:$port/messages" | grep -q "$MSG"; then
    echo "[OK]   porta $port contém '$MSG'"
  else
    echo "[FALHA] porta $port NÃO contém '$MSG'"; FAIL=1
  fi
done

echo; echo "== Arquivos no volume compartilhado =="
docker compose exec -T app1 ls -l /data

echo; echo "== Último registro de cada log =="
for n in app1 app2 app3; do
  echo "--- $n.log"; docker compose exec -T app1 tail -n 3 "/data/$n.log"
done

echo
if [ "$FAIL" -eq 0 ]; then echo "RESULTADO: replicação OK"; else echo "RESULTADO: houve falhas"; exit 1; fi
