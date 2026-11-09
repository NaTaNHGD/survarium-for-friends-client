# Cliente Survarium for Friends

- Repositorio: https://github.com/NaTaNHGD/survarium-for-friends-client.
- Esta pasta contem apenas o launcher dos jogadores e o helper do cliente. Nao adicionar servidor, banco, Client Secret, token de bot ou chave TLS privada.
- O IP 181.215.254.230 e o Application ID 1522343360004882492 sao definidos em vps_settings.py. Validar o certificado publico; nao desabilitar TLS.
- Preservar os guards nativos e a verificacao SHA256 da versao Steam suportada.
- Validacao: python -m unittest discover -q; python -m compileall -q .; python build.py. Nao ha linter configurado.
- Commitar e enviar alteracoes concluidas ao origin, sem force push.
- Nao automatizar cliques ou movimento dentro do jogo; entregar instrucoes de teste manual.
