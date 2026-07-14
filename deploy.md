# Deploy no PythonAnywhere — passo a passo

Guia completo para colocar a Fuel Consumption API no ar usando o
plano gratuito do PythonAnywhere. Para deploy em outros provedores
(Railway, Render, Fly.io, etc.) basta usar `uvicorn` direto.

## Estrutura esperada do repositório

O projeto já vem organizado assim (a `app/` é o pacote Python; o
`src/` antigo foi removido neste commit):

```
Fuel-Consumption-API/
├── app/                  ← pacote Python importável
│   ├── __init__.py
│   ├── main.py           ← FastAPI app + middleware + handlers
│   ├── config.py         ← Pydantic Settings
│   ├── errors.py         ← erros tipados
│   ├── middleware/       ← request_id, logging
│   ├── shared/           ← logger JSON
│   └── fuel/             ← rotas, schemas, service, physics, etc.
├── tests/                ← suíte pytest (219 testes, ~96% cobertura)
├── frontend/             ← interface web estática
├── requirements.txt
├── wsgi.py               ← entry point WSGI pro PythonAnywhere free
├── .env.example
├── deploy.md             ← este arquivo
└── README.md
```

---

## 1. Criar conta no PythonAnywhere

1. Acesse <https://www.pythonanywhere.com/pricing/>
2. Clique em **Create a Beginner account** (free)
3. Confirme o e-mail

**Limitações do plano free:**
- 1 web app por conta
- CPU limitado a ~100 s/dia
- 512 MB de RAM
- Domínio `seuusuario.pythonanywhere.com` (domínio próprio só no plano pago)
- Sem ASGI nativo (por isso usamos `a2wsgi` para embrulhar em WSGI)

---

## 2. Subir o código

A forma mais prática: clonar do GitHub.

No PythonAnywhere, abra o **Bash console** (Dashboard → `$ Bash`):

```bash
git clone https://github.com/0pedrohalmeida0/Fuel-Consumption-API.git
cd Fuel-Consumption-API
```

(Para atualizar depois: `git pull`)

---

## 3. Criar virtualenv e instalar dependências

```bash
cd ~/Fuel-Consumption-API
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r backend-requirements.txt
```

> **Erros comuns**:
> - "externally-managed-environment" → você esqueceu de ativar o `.venv`
> - Falha ao compilar `pydantic-core` → tente `pip install pydantic==2.9.2 --only-binary=:all:`
> - Python 3.11 não disponível → no PythonAnywhere free, as versões disponíveis são 3.10 e 3.11. Use exatamente a mesma versão que rodou localmente.

---

## 4. Configurar o Web app

1. Aba **Web** (no topo) → **Add a new web app**
2. **Next** até o framework → escolha **Manual configuration**
3. Escolha **Python 3.11**
4. Preencha:

   | Campo                       | Valor                                                       |
   |-----------------------------|-------------------------------------------------------------|
   | **Source code**             | `/home/SEU_USUARIO/Fuel-Consumption-API`                    |
   | **Working directory**       | `/home/SEU_USUARIO/Fuel-Consumption-API`                    |
   | **WSGI configuration file** | `/home/SEU_USUARIO/Fuel-Consumption-API/wsgi.py`            |
   | **Virtualenv**              | `/home/SEU_USUARIO/Fuel-Consumption-API/.venv`              |

   (Troque `SEU_USUARIO` pelo seu username do PythonAnywhere.)

5. Clique em **Save**.

---

## 5. Recarregar e testar

1. Na aba **Web**, clique no botão verde **Reload** no topo.
2. Abra o **Error log** (link na mesma página) para acompanhar.

URLs pra testar no browser:

- `https://seuusuario.pythonanywhere.com/health` → `{"status":"ok"}`
- `https://seuusuario.pythonanywhere.com/api/v1/fuel/presets` → 9 veículos
- `https://seuusuario.pythonanywhere.com/docs` → Swagger UI

Se algum endpoint der **500**, o Error log vai mostrar o traceback
completo. As causas mais comuns estão na tabela no fim deste arquivo.

---

## 6. Apontar o front-end pra API em produção

No campo "API" no topo do `frontend/index.html`, troque a URL base
para:

```
https://seuusuario.pythonanywhere.com
```

E hospede o `frontend/` em qualquer um destes (todos com plano free):

- **GitHub Pages** — basta dar push no `frontend/` numa branch `gh-pages`
- **Netlify** — drag-and-drop da pasta
- **Vercel** — `vercel deploy` na pasta

O CORS já está `cors_origins=["*"]` no `app/config.py`, então não
precisa liberar nada no back-end.

---

## 7. (Opcional) Domínio próprio

Requer plano pago (US$ 5/mês, Hacker plan):

1. Compre o domínio (Registro.br, Namecheap, etc.)
2. Crie um **CNAME** `api` → `seuusuario.pythonanywhere.com`
3. Aba **Web** → **Add a domain**
4. Aguarde a propagação DNS (até 48 h)

---

## 8. Atualizando o código depois

```bash
# local: edite, commit, push
git add -A
git commit -m "..."
git push

# no Bash do PythonAnywhere:
cd ~/Fuel-Consumption-API
git pull
# se backend-requirements.txt mudou:
source .venv/bin/activate
pip install -r requirements.txt

# volte na aba Web e clique em Reload
```

---

## Rodando os testes no PythonAnywhere (opcional)

Você pode rodar a suíte pytest direto no console bash pra garantir
que tudo continua passando depois de uma atualização:

```bash
cd ~/Fuel-Consumption-API
source .venv/bin/activate
pytest -q
```

Esperado: **219 passed** com cobertura ~96%.

---

## Se você tiver o plano Hacker (pago)

Tem suporte ASGI nativo. Nesse caso:

1. **Web** → **Add a new web app** → **Asynchronous (ASGI)**
2. Crie `asgi.py` na raiz:
   ```python
   from app.main import app
   application = app
   ```
3. Aponte o **ASGI configuration file** pra esse `asgi.py`
4. Pode remover `a2wsgi` do `requirements.txt`

---

## Erros comuns e como resolver

| Sintoma                                              | Causa provável                                          | Solução                                                       |
|------------------------------------------------------|---------------------------------------------------------|---------------------------------------------------------------|
| 500 logo de cara                                     | `application` não foi encontrado                        | Confira o path do **WSGI configuration file**                 |
| `ModuleNotFoundError: app`                           | `sys.path` não inclui a raiz                            | Confirme o `wsgi.py` (ele faz `sys.path.insert(0, BASE_DIR)`) |
| `ModuleNotFoundError: No module named 'app.fuel'`    | Repo ainda com layout antigo (`src/`)                   | Faça `git pull` (o repo já está reestruturado)               |
| `ModuleNotFoundError: No module named 'app.main'`    | `wsgi.py` ou `app/main.py` faltando                     | Verifique se `git clone` baixou tudo                          |
| 500 só nas rotas `/api/...`                          | `a2wsgi` não instalado                                 | `pip install a2wsgi` no venv                                  |
| CORS error no browser                                | CORS não está liberado                                  | `cors_origins=["*"]` no `.env` ou `app/config.py`             |
| Web app não atualiza                                 | Worker antigo em memória                                | Clique em **Reload** (não só Save) na aba Web                 |
| `H14 No such file or directory`                      | **Working directory** errado                            | Coloque o mesmo path do **Source code**                       |
| Funciona local mas não no PA                         | Versão de Python diferente                              | Use exatamente a mesma versão (3.11) em ambos                |
| `DisallowedHost` no log                              | Host header do PythonAnywhere não bate                  | Ajuste `cors_origins` no `.env` ou desabilite a validação    |
| `BadRequest` no batch                                | Lista maior que `BATCH_SIZE_LIMIT` (default 100)        | Reduza a lista ou aumente o limite via `.env`                 |

---

Dica final: mantenha o **Error log** aberto numa aba enquanto
testa — ele atualiza em tempo real e mostra exatamente onde
a app travou na inicialização.
