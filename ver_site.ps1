# Atualiza o arquivo privado (resultados da última noite) e abre o site no browser.
# Correr com:  .\ver_site.ps1      (na pasta do motor; o arquivo está em ..\arena-arquivo)
param([string]$Arquivo = (Join-Path $PSScriptRoot "..\arena-arquivo"))
git -C $Arquivo pull -q
Start-Process (Join-Path $Arquivo "site\index.html")
