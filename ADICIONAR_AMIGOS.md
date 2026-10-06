# ➕ Como liberar amigos para usar o bot (automático)

O bot está no modo **"Testando"** do Google. Por isso, para um amigo conseguir
conectar o Google dele, o e-mail dele precisa estar na lista de **Usuários de
teste**. Esta ferramenta faz isso por você automaticamente.

## Passo a passo

1. Dê **duplo clique** em:

   ```
   adicionar_teste.bat
   ```

2. Na janela que abrir:
   - Cole o **e-mail do seu amigo** (pode ser mais de um, separados por vírgula)
   - Clique em **"Adicionar ao Google"**

3. Na **primeira vez**, vai abrir o **Brave** num perfil novo:
   - Faça login com **`thiagofbg52@gmail.com`** (a conta dona do projeto)
   - Esse login fica salvo para as próximas vezes

4. Pronto! Quando aparecer **"✅ E-mail adicionado!"**, o amigo já pode:

   - Abrir **https://t.me/mini_thiago_bot**
   - Enviar **`/conectar`** e autorizar (ele verá o aviso "app não verificado" →
     **Avançado → Acessar (não seguro)**)

## Como funciona por dentro

- Abre o seu navegador real (Brave/Chrome/Edge) com depuração remota
- Conecta o robô (Playwright) nele
- Navega até a tela **Google Auth Platform → Público-alvo → Usuários de teste**
- Preenche o e-mail e clica em **Salvar**

> ℹ️ É automação de tela (o Google não tem API para isso). Se o Google mudar o
> layout, pode ser necessário ajustar os seletores em `adicionar_teste.py`.

## Se der erro

- Veja o arquivo **`automacao.log`** (tem o passo a passo e o erro exato)
- Um print da tela é salvo em **`erro_automacao.png`**

## Limites

- Total de usuários de teste: **100**
- Para atender **qualquer pessoa sem limite**, é preciso **publicar** o app, o que
  exige um **domínio próprio verificado** (ex.: `agenda-thiago.com.br`).
