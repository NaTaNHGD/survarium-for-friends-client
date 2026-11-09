# Survarium for Friends - jogador

Repositorio independente: https://github.com/NaTaNHGD/survarium-for-friends-client.
Servidor: https://github.com/NaTaNHGD/survarium-for-friends.

## Baixar e jogar (Windows x64)

1. Abra [Releases](https://github.com/NaTaNHGD/survarium-for-friends-client/releases/latest) e, em **Assets**, baixe **SurvariumFriends-Cliente.zip**. Nao baixe **Source code** nem **Code > Download ZIP**: esses arquivos contem somente o codigo, sem executavel.
2. Extraia o ZIP inteiro. Dentro da pasta **SurvariumFriends**, abra **SurvariumFriends.exe**. Mantenha a pasta `_internal` junto do executavel; nao precisa instalar Python.
3. Clique em **Localizar jogo** e selecione `game/binaries/x64/survarium.exe` da versao Steam compativel **0.69d0**.
4. Na primeira abertura, clique em **Conectar Discord** e autorize o aplicativo no navegador. O login fica salvo para as proximas aberturas.
5. Clique em **Conectar**. O destino fixo e `181.215.254.230`. O jogo abre em ingles.

O administrador precisa liberar seu ID Discord na aba Contas da VPS. O ID e obtido pelo Discord, nao digitado como identidade pelo launcher. A versao 0.2.0 restaura o login automaticamente, renova sessoes expiradas e aceita mudanca do IP de internet sem exigir nova autorizacao no navegador. Requer o servidor atualizado para a mesma versao de acesso OAuth; servidores antigos continuam aceitando login manual, mas nao oferecem a renovacao.

O Windows protege a credencial de renovacao para o usuario atual com DPAPI, no arquivo `discord-login.dpapi`. **Esquecer conta** remove o login salvo deste PC; nao apaga inventario ou progresso na VPS. **Trocar conta** abre uma nova autorizacao. Nao copie esse arquivo entre PCs nem compartilhe a pasta de preferencias. Se a autorizacao for revogada no Discord, sera necessario conectar novamente.

O login usa HTTPS com o certificado privado desta instalacao. O retorno do navegador e somente `http://127.0.0.1:65110/callback` no seu PC. Nao abra essa porta no roteador. O launcher nao possui o Client Secret, token do bot, banco de jogadores nem servidor embutido.

Preferencias e logs ficam em `%LOCALAPPDATA%\SurvariumForFriends`. Nao compartilhe essa pasta. Os perfis e saldos ficam na VPS, vinculados ao Discord. Ao fechar o launcher, o helper do jogo permanece ativo ate o jogo encerrar.

Esta entrega habilita login e perfis remotos. O modo atual ainda executa bots localmente em cada cliente: nao comprova que dois jogadores participem da mesma partida. A replicacao de mundo compartilhado continua pendente.

## Desenvolvimento

Python 3.13 x64. Execute `Preparar-Dependencias.cmd`, depois `python -m unittest discover -q` e `python build.py`.
O ZIP fica em `dist/SurvariumFriends-Cliente.zip`. Binarios e dependencias nao sao versionados.
O certificado publico desta VPS e versionado; a chave privada permanece somente na distribuicao do servidor.
Nao recrie o certificado ou desabilite TLS para contornar erros de configuracao.

Na VPS, configure o Client Secret e o redirect URI descritos em `VPS-PUBLICA.md` do repositorio do servidor.
O fluxo segue [OAuth2 do Discord](https://docs.discord.com/developers/topics/oauth2), com authorization code, PKCE e `state`.
