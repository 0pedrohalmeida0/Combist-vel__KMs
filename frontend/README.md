# Fuel Consumption API — Front-end

Interface web estática (HTML + CSS + JavaScript vanilla) que consome a
[API de cálculo de combustível](../app/). Sem build step, sem
dependências locais (Chart.js via CDN).

## Como rodar local

```bash
# do diretório raiz do repositório
python3 -m http.server 8080
# Abra: http://localhost:8080/frontend/
```

> Não funciona abrir `index.html` direto pelo `file://` — o `fetch`
> pra API é bloqueado por CORS do protocolo `file://`.

## Como usar

1. No topo da página, configure a **URL base da API** (ex.:
   `https://seuusuario.pythonanywhere.com`). O indicador verde/vermelho
   ao lado mostra se a API está respondendo.
2. Escolha um **preset de veículo** ou marque *Especificações
   customizadas*.
3. Preencha os parâmetros da viagem (distância é o único obrigatório).
4. Clique em **Calcular**.

A URL da API é salva no `localStorage`, então não precisa redigitar
toda vez.

## Como hospedar no Netlify

O jeito mais fácil é conectar o GitHub ao Netlify — push na `main`
faz redeploy automático.

**Opção 1: via interface do Netlify (sem CLI)**

1. Suba o repo pro GitHub (você já fez isso).
2. Acesse <https://app.netlify.com/start> e conecte sua conta GitHub.
3. Selecione o repo `Fuel-Consumption-API`.
4. Configure:
   - **Build command**: deixe vazio
   - **Publish directory**: `frontend`
5. Clique em **Deploy site**. Em ~30 s, o front-end está no ar
   numa URL tipo `https://random-name-12345.netlify.app`.
6. (Opcional) **Site settings → Change site name** pra um domínio
   customizado tipo `fuel-comb.netlify.app`.

**Opção 2: via CLI (pra deploys manuais)**

```bash
npm install -g netlify-cli
netlify login
netlify init   # primeira vez, escolhe "create new site"
netlify deploy --dir=frontend --prod
```

Aí você também pode usar `netlify deploy --dir=frontend` (sem
`--prod`) pra fazer deploy de **preview** num URL temporário antes
de mandar pra produção.

**Opção 3: drag-and-drop (mais rápida pra testar)**

1. Acesse <https://app.netlify.com/drop>.
2. Arraste a pasta `frontend/` direto na página.
3. Pronto — site no ar em segundos, sem precisar conectar GitHub.

## Configurando a URL da API após o deploy

Após o primeiro deploy, abra o site no ar e:

1. No campo **API** no topo da página, digite a URL do seu back-end
   (ex.: `https://seuusuario.pythonanywhere.com`).
2. Aperte **Enter** ou saia do campo — a URL fica salva no
   `localStorage` do navegador.

**OU**, melhor: habilite o **proxy reverso** no `netlify.toml`
(descomente o bloco `[[redirects]]` que aponta `/api/*` pro seu
PythonAnywhere). Aí você usa URL relativa `/api/v1/fuel/...` e:

- CORS vira problema de servidor (mesma origem = sem preflight)
- A URL do back-end fica escondida do público
- Não precisa configurar nada no campo "API" — funciona de cara

Depois de descomentar, lembre de trocar `DEFAULT_API` em
`frontend/app.js` pra string vazia (`const DEFAULT_API = '';`) e
dar push. O site vai rebuildar sozinho.

## Stack

- HTML5 puro
- CSS puro com variáveis (suporta dark/light mode automático)
- JavaScript ES2020, sem build
- [Chart.js 4.4](https://www.chartjs.org/) via CDN (gráfico de fatores)

## Estrutura

```
frontend/
├── index.html     # página única
├── styles.css     # tema dark/light responsivo
├── app.js         # lógica (fetch, parse, render, validação)
├── _headers       # cabeçalhos de segurança (Netlify)
├── _redirects     # regras de proxy/redirect (Netlify)
└── README.md      # este arquivo
```

## Limitações conhecidas

- O breakdown por segmento mostra os primeiros 50 (~5 km). Viagens
  maiores mostram `+N segmentos` no fim.
- Sem histórico de cálculos nesta versão.
- Sem autenticação — a API está aberta a qualquer um que souber a URL.
