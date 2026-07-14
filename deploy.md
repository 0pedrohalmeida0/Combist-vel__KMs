# Deploy no PythonAnywhere — passo a passo

Guia completo para colocar a Fuel Consumption API no ar usando o
plano gratuito do PythonAnywhere. Para deploy em outros provedores
(Railway, Render, Fly.io, etc.) basta usar `uvicorn` direto.

## ⚠️ Antes de tudo: estrutura do repositório

O back-end neste repo está em `src/` mas os imports esperam o pacote
`app.fuel.*` (veja `src/routes.py` → `from app.fuel.schemas import ...`).
Para a app rodar, o código precisa estar nessa estrutura:

```
Fuel-Consumption-API/
├── app/                  ← o pacote Python
│   ├── __init__.py
│   ├── main.py           ← FastAPI app
│   ├── config.py         ← Settings
│   ├── errors.py         ← erros tipados
│   ├── middleware/
│   ├── shared/
│   └── fuel/
│       ├── __init__.py
│       ├── routes.py     ← era src/routes.py
│       ├── service.py    ← era src/service.py
│       ├── schemas.py    ← era src/schemas.py
│       ├── physics.py    ← era src/physics.py
│       ├── corrections.py
│       ├── repository.py
│       └── presets.py
├── requirements.txt
├── wsgi.py
└── frontend/
```

**Se você ainda não fez essa reestruturação**, siga o roteiro da
seção [0. Reestruturar o repositório](#0-reestruturar-o-repositório)
mais abaixo antes de continuar.

---

## 0. Reestruturar o repositório

Esse é o caminho mais limpo. Se preferir, pode pular essa etapa
caso seu repo já tenha a estrutura `app/fuel/...` — passe direto
para [1. Preparar o projeto](#1-preparar-o-projeto).

```bash
# local, na raiz do repo
mkdir -p app/fuel
touch app/__init__.py app/fuel/__init__.py

mv src/corrections.py app/fuel/corrections.py
mv src/physics.py     app/fuel/physics.py
mv src/presets.py     app/fuel/presets.py
mv src/repository.py  app/fuel/repository.py
mv src/routes.py      app/fuel/routes.py
mv src/schemas.py     app/fuel/schemas.py
mv src/service.py     app/fuel/service.py

rmdir src
```

Crie também `app/main.py`, `app/config.py`, `app/errors.py` e a pasta
`app/middleware/` (veja a versão de referência em
<https://github.com/seu-repo/Fuel-Consumption-API/blob/main/app/>).

Depois faça `git add -A && git commit -m "Restructure: src/ → app/fuel/"`.

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
- Sem ASGI nativo (por isso precisamos do `a2wsgi`)

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
pip install -r requirements.txt
```

> **Erros comuns**:
> - "externally-managed-environment" → você esqueceu de ativar o `.venv`
> - Falha ao compilar `pydantic-core` → tente `pip install pydantic==2.9.2 --only-binary=:all:`
> - Python 3.11 não disponível → no PythonAnywhere free, as versões
>   disponíveis são 3.10 e 3.11. Use exatamente a mesma versão que
>   rodou localmente.

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
# se requirements.txt mudou:
source .venv/bin/activate
pip install -r requirements.txt

# volte na aba Web e clique em Reload
```

---

## Se você tiver o plano Hacker (pago)

Tem suporte ASGI nativo. Nesse caso:

1. **Web** → **Add a new web app** → **Asynchronous (ASGI)**
2. Crie `asgi.py` na raiz:
   ```python
   import sys
   from pathlib import Path
   sys.path.insert(0, str(Path(__file__).parent / "app"))
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
| `ModuleNotFoundError: app`                           | `sys.path` não inclui o pacote                          | Confira o `wsgi.py` (ele faz `sys.path.insert(0, "src")` ou `"app"`) |
| `ModuleNotFoundError: No module named 'app.fuel'`    | Repo ainda com layout antigo (`src/` em vez de `app/`)  | Siga a seção 0 (Reestruturar)                                 |
| 500 só nas rotas `/api/...`                          | `a2wsgi` não instalado                                 | `pip install a2wsgi` no venv                                  |
| CORS error no browser                                | CORS não está liberado                                  | `cors_origins=["*"]` no `app/config.py`                       |
| Web app não atualiza                                 | Worker antigo em memória                                | Clique em **Reload** (não só Save) na aba Web                 |
| `H14 No such file or directory`                      | **Working directory** errado                            | Coloque o mesmo path do **Source code**                       |
| Funciona local mas não no PA                         | Versão de Python diferente                              | Use exatamente a mesma versão (3.11) em ambos                |
| `DisallowedHost` no log                              | Host header do PythonAnywhere não bate                  | Middleware TrustHost do FastAPI resolve, ou ajuste `cors_origins` |

---

Dica final: mantenha o `Error log` aberto numa aba enquanto
testa — ele atualiza em tempo real e mostra exatamente onde
a app travou na inicialização.
