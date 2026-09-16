# Copy all matching plugin modules with the supported installer.
& (Join-Path $PSScriptRoot '..\install-plugin.ps1') @args
