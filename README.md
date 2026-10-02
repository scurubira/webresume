# CV Link

Upload de currículo PDF, link curto, notificações de acesso ao proprietário **e construtor de currículos com exportação para PDF ou DOCX**.

## Executar

Python 3.12+, sem dependências externas:

```bash
PORT=8001 python3 server.py
```

Abra http://localhost:8001. **Não use `python3 -m http.server` nem abra o HTML diretamente:** o upload, as notificações e a exportação DOCX precisam de `server.py`.

## Criar currículo

Acesse http://localhost:8001/builder.html para usar o construtor:

1. Preencha dados pessoais, resumo, experiência, formação e habilidades.
2. Escolha entre três templates: Clássico, Moderno ou Minimal.
3. Exporte para PDF usando o botão de imprimir otimizado para A4.
4. Exporte para DOCX; o arquivo é gerado pelo servidor usando apenas a biblioteca padrão.

Os dados do editor são salvos localmente no navegador e não são enviados ao servidor até o momento da exportação DOCX.

Os arquivos e registros persistem em `data/`, que não é publicado nem incluído no Git. O servidor só expõe os arquivos estáticos permitidos e o PDF por link público. O painel exige uma chave privada aleatória, cuja hash fica no banco. As chaves são guardadas no navegador; limpar o armazenamento sem uma cópia da chave perde o acesso ao painel.

## E-mail

Configure `SMTP_HOST`, `SMTP_PORT` (padrão 587 com STARTTLS), `SMTP_FROM`, `SMTP_USER` e `SMTP_PASSWORD` no ambiente. Consulte `.env.example`. A aplicação **não lê arquivos .env automaticamente**. Use uma senha de aplicativo ou credencial SMTP do provedor. Não coloque senhas no código ou no Git.

Sem SMTP, o upload funciona e o histórico mostra “E-mail não configurado”; nenhum e-mail real é enviado. Com SMTP, o envio roda em segundo plano e o painel distingue fila, sucesso e falha. Esta versão não tem fila durável nem repetição automática de e-mails que falharam ou foram interrompidos por reinício.

## Compartilhamento externo

`localhost` funciona só na máquina local. Para recrutadores externos, hospede o servidor em uma URL HTTPS acessível, configure `PUBLIC_BASE_URL` com essa URL e mantenha armazenamento persistente. Configure `HOST=0.0.0.0` quando exigido pela hospedagem. Links curtos usam o domínio da própria aplicação, sem um serviço externo.

## O que conta como acesso

A solicitação GET do PDF registra um acesso. HEAD não registra. Reaberturas do mesmo navegador em 60 segundos são agrupadas por um cookie anônimo. Sem cookies, solicitações podem contar separadamente. Pré-visualizadores e robôs também podem solicitar PDFs: um evento não confirma que uma pessoa leu o currículo, nem identifica o visitante. Quem possui o link pode acessar o arquivo. A página pública informa sobre o registro.

## Verificação

```bash
python3 -m unittest -v test_server.py
```

Esta é uma implementação inicial. Antes de hospedar para uso público em escala, adicione limites de upload por usuário/IP, controle de abuso, análise de arquivos, política de retenção/exclusão, autenticação de contas e fila de e-mail persistente. O servidor HTTP da biblioteca padrão serve ao desenvolvimento; use infraestrutura de aplicação apropriada para produção.
