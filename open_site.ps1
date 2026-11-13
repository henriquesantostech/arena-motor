# Updates the private archive (results of the latest night) and opens the site in the browser.
# Run with:  .\ver_site.ps1      (from the engine folder; the archive lives in ..\arena-arquivo)
param([string]$Archive = (Join-Path $PSScriptRoot "..\arena-arquivo"))
git -C $Archive pull -q
Start-Process (Join-Path $Archive "site\index.html")
