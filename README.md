# MeuDinDin

> Assistente financeiro para todos os momentos.

Assistente financeiro pessoal: veja quanto tem, quanto guardou e quanto falta para suas metas sem abrir o app do banco.

- **Login e cadastro** com JWT (access token em memória, refresh token em cookie httpOnly com rotação e blacklist)
- **Lançamentos** de entradas e gastos, avulsos ou recorrentes (diário, semanal, mensal), com categorias
- **Dashboard** com visão diária, semanal e mensal: saldo, entradas, gastos, gráfico, gastos por categoria
- **Metas** com progresso, quanto falta e quanto guardar por mês até o prazo
- **Metas em conjunto**: convide pessoas por e-mail; cada participante guarda dinheiro e vê a parte de cada um

## Stack

| Camada | Tecnologia |
|---|---|
| Backend | Python 3.12+, Django 6, Django REST Framework, SimpleJWT |
| Frontend | React 19, TypeScript, Vite, React Router, TanStack Query, Recharts |
| Banco | PostgreSQL no [Neon](https://neon.tech) (ou SQLite local quando `DATABASE_URL` está vazio) |

## Como rodar

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env        # ajuste DJANGO_SECRET_KEY
python manage.py migrate
python manage.py createsuperuser   # opcional, para o /admin
python manage.py runserver
```

### Banco no Neon

1. Crie um projeto em [console.neon.tech](https://console.neon.tech) (região São Paulo, `sa-east-1`, se disponível).
2. Em **Connect**, marque **Connection pooling** e copie a connection string.
3. Cole no `backend/.env` em `DATABASE_URL=` e rode `python manage.py migrate`.

Com `DATABASE_URL` vazio o projeto usa SQLite local. Os testes (`manage.py test`) sempre usam SQLite, mesmo com o Neon configurado.

Depois do primeiro `migrate`, crie a tabela de cache (usada pelo bloqueio de login): `python manage.py createcachetable`.

### E-mail (Brevo)

No `backend/.env`, preencha `BREVO_SMTP_LOGIN` e `BREVO_SMTP_KEY` (Brevo > Settings > SMTP & API > SMTP) e `EMAIL_FROM` com um remetente verificado no Brevo. Sem a chave, os e-mails (códigos e convites) aparecem no terminal do Django. Todo e-mail sai com o cabeçalho `X-Mailin-Tag: meudindin`.

### Frontend (outro terminal)

```powershell
cd frontend
npm install
npm run dev
```

Acesse **http://localhost:5173**. O Vite repassa `/api` para o Django em `127.0.0.1:8000`.

### Testes

```powershell
cd backend
python manage.py test        # 30 testes: auth, lançamentos, recorrência, dashboard, metas
cd ../frontend
npm run build && npm run lint
```

## Deploy (Render + Neon + Brevo)

Um único serviço Docker no Render: o `Dockerfile` compila o React e o Django serve a API e o front no mesmo domínio (o cookie de login `SameSite=Strict` funciona sem CORS). Na inicialização, `backend/start.sh` aplica as migrações e sobe o Gunicorn.

1. No Render: **New > Blueprint** e escolha este repositório (o `render.yaml` cria o serviço).
2. Preencha as variáveis pedidas:
   - `DATABASE_URL`: connection string *pooled* do Neon
   - `DATA_ENCRYPTION_KEY`: **o mesmo valor** do `backend/.env` local, se os dois usam o mesmo banco
   - `BREVO_API_KEY`: chave de **API** do Brevo (`xkeysib-...`). O plano free do Render bloqueia SMTP
   - `EMAIL_FROM`: remetente verificado no Brevo
   - `FRONTEND_URL`: a URL do serviço, ex. `https://meudindin.onrender.com` (usada nos links dos e-mails)
3. Health check: `/api/health/` (testa também a conexão com o banco).

No plano free o serviço "dorme" após 15 minutos sem acesso; o primeiro acesso depois disso leva cerca de 1 minuto.

## API

| Método | Rota | Descrição |
|---|---|---|
| POST | `/api/auth/register/` | Cadastro pendente; envia código de 6 dígitos por e-mail |
| POST | `/api/auth/verify-email/` | Confirma o e-mail com o código e entra |
| POST | `/api/auth/resend-code/` | Reenvia o código (intervalo mínimo de 60 s) |
| POST | `/api/auth/login/` | Login; 5 erros seguidos no mesmo e-mail bloqueiam por 5 minutos |
| POST | `/api/auth/login/2fa/` | Segunda etapa do login: código do app autenticador ou de recuperação |
| GET | `/api/auth/2fa/` | Status do 2FA e códigos de recuperação restantes |
| POST | `/api/auth/2fa/setup/` | Gera QR code e chave para o app autenticador |
| POST | `/api/auth/2fa/enable/` | Ativa o 2FA com o primeiro código (devolve 10 códigos de recuperação) |
| POST | `/api/auth/2fa/disable/` | Desativa (exige senha e código) |
| POST | `/api/auth/2fa/recovery-codes/` | Gera novos códigos de recuperação |
| POST | `/api/auth/password-reset/` | Envia código para redefinir a senha |
| POST | `/api/auth/password-reset/confirm/` | Nova senha com o código (encerra todas as sessões) |
| POST | `/api/auth/refresh/` | Novo access token via cookie |
| POST | `/api/auth/logout/` | Invalida o refresh token |
| GET/PATCH | `/api/auth/me/` | Perfil |
| CRUD | `/api/categories/` | Categorias do usuário |
| CRUD | `/api/transactions/` | Filtros: `kind`, `period`, `start`, `end`, `category`, `search` |
| GET | `/api/dashboard/?period=daily\|weekly\|monthly` | Resumo para o dashboard |
| CRUD | `/api/goals/` | Metas em que o usuário participa |
| GET/POST | `/api/goals/{id}/contributions/` | Histórico / guardar (valor negativo = retirar) |
| POST | `/api/goals/{id}/invite/` | Convidar por e-mail (só o dono) |
| POST | `/api/goals/{id}/invites/{invite_id}/cancel/` | Cancelar convite (só o dono) |
| DELETE | `/api/goals/{id}/members/{user_id}/` | Remover participante (só o dono) |
| POST | `/api/goals/{id}/leave/` | Sair da meta |
| GET | `/api/invites/` | Convites recebidos |
| POST | `/api/invites/{id}/accept/` e `/decline/` | Responder convite |

## Regras de negócio

- **Recorrência**: o lançamento original é o modelo; as ocorrências até hoje são geradas automaticamente ao abrir lançamentos ou o dashboard. Mudar a recorrência para "Único" para a geração.
- **Saldo disponível** = entradas − gastos − o que você guardou em metas.
- **Convites**: a pessoa vê o convite ao entrar com o e-mail convidado (se ainda não tem conta, vê assim que se cadastrar). Não há envio de e-mail.
- **Permissões**: qualquer participante vê a meta e guarda dinheiro; só o dono edita, exclui, convida e remove pessoas. Ninguém retira mais do que guardou.

## Segurança

- **2FA (TOTP)** opcional por app autenticador, ativado em Segurança. Segredo criptografado (Fernet), códigos de uso único (anti-replay), 10 códigos de recuperação com hash. Erros no código contam para o bloqueio de login.
- **Sessão** expira após 15 minutos sem uso: access token de 5 min e refresh token de 15 min renovado só enquanto há atividade; aviso 1 minuto antes; sincronizado entre abas.

Senhas com hasher padrão do Django (PBKDF2) e validadores de força; mensagens de login genéricas; rate limit em auth; isolamento por usuário em todas as consultas (recurso de outro usuário retorna 404); validação de categoria contra IDOR; `SECRET_KEY` via ambiente; HSTS, cookies seguros e redirect HTTPS quando `DJANGO_DEBUG=False`.
