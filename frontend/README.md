# Fuel Consumption API — Front-end

Interface web estática (HTML + CSS + JavaScript vanilla) que consome a
[API de cálculo de combustível](../src/). Sem build step, sem
dependências locais (Chart.js via CDN).

## Como rodar

A forma mais simples é subir um servidor HTTP estático na raiz do
projeto (a pasta `frontend/` é servida diretamente):

```bash
# do diretório raiz do repositório
python3 -m http.server 8080
```

Abra <http://localhost:8080/frontend/> no navegador.

### Outras opções

| Comando                                                | Onde abre                          |
|--------------------------------------------------------|------------------------------------|
| `python3 -m http.server 8080` (na raiz)                | <http://localhost:8080/frontend/>  |
| `npx serve .`                                          | URL mostrada no terminal           |
| Abrir `frontend/index.html` direto no navegador        | ⚠️ Não funciona — fetch é bloqueado por CORS do `file://` |

## Como usar

1. No topo da página, configure a **URL base da API** (ex.:
   `http://localhost:8000`). O indicador verde/vermelho ao lado mostra
   se a API está respondendo.
2. Escolha um **preset de veículo** (recomendado) ou marque
   *Especificações customizadas* e preencha manualmente.
3. Preencha os parâmetros da viagem (distância é o único obrigatório).
4. Clique em **Calcular** e veja o resultado no painel à direita:
   - Métricas principais (combustível total, consumo médio, duração, energia)
   - Gráfico de contribuição de cada fator de correção
   - Avisos (pneu murcho, AC no frio, tanque pequeno etc.)
   - Breakdown opcional por segmento de 100 m

A URL da API é salva no `localStorage`, então não precisa redigitar.

## Stack

- HTML5 sem framework
- CSS puro com variáveis e suporte a dark/light mode automático
- JavaScript ES2020, sem build
- [Chart.js 4.4](https://www.chartjs.org/) via CDN (apenas para o gráfico de fatores)

## Estrutura

```
frontend/
├── index.html     # página única
├── styles.css     # tema dark/light responsivo
├── app.js         # lógica (fetch, parse, render, validação)
└── README.md      # este arquivo
```

## Limitações conhecidas

- O breakdown por segmento mostra os primeiros 50 segmentos (≈ 5 km).
  Para viagens maiores, a tabela exibe um rodapé `+N segmentos`.
- A UI assume que a API está rodando no mesmo host ou com CORS
  liberado. Se a API estiver em outro domínio, libere o CORS no
  `main.py` (já vem com `cors_origins=["*"]` por padrão).
- Não há histórico de cálculos nesta versão.
