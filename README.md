# Sistema de mensagens distribuído (Flask + Docker Compose)

Três instâncias do mesmo serviço (`app1`, `app2`, `app3`) trocam mensagens entre si
e gravam tudo em um volume compartilhado.

## Estrutura
```
avaliacao/
├── app/
│   ├── app.py            # serviço REST + replicação
│   ├── requirements.txt  # flask, requests, gunicorn
│   └── Dockerfile
├── docker-compose.yml
├── test.sh
└── README.md
```

## Como executar
```bash
docker compose up -d --build     # sobe app1, app2 e app3
./test.sh                        # teste automático de replicação
docker compose down              # para
```

Teste manual:
```bash
curl -X POST -H "Content-Type: application/json" -d '{"message":"hello"}' http://localhost:5001/send
curl http://localhost:5002/messages
curl http://localhost:5003/messages
```

## Endpoints
| Método | Rota | Descrição |
|---|---|---|
| POST | `/send` | Recebe `{"message": "texto"}`, grava e replica para os outros dois nós |
| GET | `/messages` | Retorna todas as mensagens gravadas pelo nó |

Portas no host: app1 → 5001, app2 → 5002, app3 → 5003 (todas 5000 dentro do container).

## Como funciona
1. O cliente faz `POST /send` em qualquer instância.
2. A instância cria o registro (`id` UUID, `message`, `origin`, `timestamp`) e grava em
   `/data/messages_<nó>.jsonl`.
3. Em seguida usa `requests` para enviar uma cópia a cada peer (`http://app2:5000/send`),
   resolvendo o nome pelo DNS da rede `msgnet`.
4. A cópia leva o cabeçalho `X-Replicated: true`. Quem recebe só grava e **não repassa**,
   evitando laço infinito de replicação.
5. Cada nó grava seu log em `/data/<nó>.log`.

## Decisões de projeto
- **Um arquivo de mensagens por nó** dentro do mesmo volume: duas instâncias nunca escrevem
  no mesmo arquivo, então não há condição de corrida entre containers. Dentro de cada
  container um `threading.Lock` protege a escrita (gunicorn com 1 worker e 4 threads).
- **Idempotência por `id`**: se a mesma cópia chegar duas vezes, não é duplicada.
- **Tolerância a falhas**: se um peer estiver fora, a replicação falha com timeout de 2 s,
  é registrada no log e o `POST` responde com o status de cada peer.
- **Compose**: âncora YAML (`x-app`) evita repetição; rede bridge `msgnet` própria; volume
  nomeado `msgdata`.

## Verificando a replicação
`./test.sh` envia uma mensagem à app1, confere se aparece em 5001/5002/5003 e lista os
arquivos e logs do volume. Também dá para inspecionar direto:
```bash
docker compose exec app1 ls -l /data
docker compose exec app1 cat /data/messages_app3.jsonl
```

## Limitações conhecidas
Replicação síncrona e sem fila: se um peer estiver fora no momento do envio, ele não
recebe essa mensagem depois (não há reenvio). Para corrigir isso, eu utilizaria um message broker (RabbitMQ, Redis, etc).
