<#
.SYNOPSIS
    Cleanup en init van de MatchFitAI repo (met PadelAnalysis als submap, geen git-historiek).

.NOTES
    - Draai dit script VANUIT de MatchFitAI folder, of pas $ProjectPath hieronder aan.
    - Er wordt gepauzeerd (met bevestiging) vlak voor de commit en vlak voor de push,
      zodat je telkens de git status / diff kan nakijken.
#>

$ErrorActionPreference = "Stop"
$ProjectPath = "C:\Users\verbekki\OneDrive - Spraying Systems Co\Private\MatchFitAI"

Set-Location $ProjectPath
Write-Host "Werkmap: $ProjectPath" -ForegroundColor Cyan

# --- 1. Backup ---
$backupFile = "..\MatchFitAI_backup_$(Get-Date -Format yyyyMMdd_HHmmss).zip"
Write-Host "`n[1/8] Backup maken naar $backupFile ..." -ForegroundColor Cyan
Compress-Archive -Path "." -DestinationPath $backupFile -Force
Write-Host "Backup klaar." -ForegroundColor Green

# --- 2. Scan op .git folders en mogelijke secrets ---
Write-Host "`n[2/8] Scannen op .git folders..." -ForegroundColor Cyan
$gitFolders = Get-ChildItem -Path . -Recurse -Force -Directory -Filter ".git" -ErrorAction SilentlyContinue
$gitFolders | ForEach-Object { Write-Host "  Gevonden: $($_.FullName)" -ForegroundColor Yellow }

Write-Host "`n[2/8] Scannen op mogelijke secrets/credentials..." -ForegroundColor Cyan
$secretFiles = Get-ChildItem -Path . -Recurse -Force -File -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -match "serviceAccount|firebase-adminsdk|\.env($|\.)|secrets|credential|\.pem$|\.key$" }
if ($secretFiles) {
    Write-Host "  LET OP - mogelijke gevoelige bestanden gevonden:" -ForegroundColor Red
    $secretFiles | ForEach-Object { Write-Host "    $($_.FullName)" -ForegroundColor Red }
} else {
    Write-Host "  Geen voor de hand liggende secret-bestanden gevonden." -ForegroundColor Green
}

# --- 3. Verwijder .git van PadelAnalysis (indien aanwezig) ---
Write-Host "`n[3/8] Verwijderen van PadelAnalysis\.git (indien aanwezig)..." -ForegroundColor Cyan
$padelGit = Join-Path $ProjectPath "PadelAnalysis\.git"
if (Test-Path $padelGit) {
    Remove-Item -Path $padelGit -Recurse -Force
    Write-Host "  Verwijderd: $padelGit" -ForegroundColor Green
} else {
    Write-Host "  Niet gevonden (al verwijderd of andere naam) - controleer bovenstaande scan." -ForegroundColor Yellow
}

# --- 4. .gitignore aanmaken (enkel als hij nog niet bestaat) ---
Write-Host "`n[4/8] .gitignore aanmaken (indien nog niet aanwezig)..." -ForegroundColor Cyan
if (-not (Test-Path ".gitignore")) {
@"
# Python
__pycache__/
*.pyc
.venv/
venv/
env/
*.egg-info/

# Secrets / credentials
*.env
.env.*
*serviceAccount*.json
firebase-adminsdk*.json
*credentials*.json
*.pem
*.key
.streamlit/secrets.toml

# Backups / temp
*.bak
*.backup
*_backup*
*.old
*~
*.tmp

# OS / editor
.DS_Store
Thumbs.db
.vscode/
.idea/

# Node
node_modules/

# Logs
*.log
"@ | Out-File -FilePath ".gitignore" -Encoding utf8
    Write-Host "  .gitignore aangemaakt." -ForegroundColor Green
} else {
    Write-Host "  .gitignore bestaat al, wordt niet overschreven." -ForegroundColor Yellow
}

# --- 5. git init + eerste commit met enkel .gitignore ---
Write-Host "`n[5/8] git init..." -ForegroundColor Cyan
if (-not (Test-Path ".git")) {
    git init
} else {
    Write-Host "  .git bestaat al in de root - init overgeslagen." -ForegroundColor Yellow
}
git add .gitignore
git commit -m "Initial commit: add .gitignore" --allow-empty

# --- 6. Alles toevoegen en STOPPEN voor controle ---
Write-Host "`n[6/8] Bestanden stagen (git add -A)..." -ForegroundColor Cyan
git add -A

Write-Host "`n===== GIT STATUS - CONTROLEER DIT ZORGVULDIG =====" -ForegroundColor Magenta
git status

Write-Host "`nControleer hierboven of er GEEN venv/, node_modules/, .env, of secret-bestanden staan." -ForegroundColor Magenta
$confirm1 = Read-Host "`nAlles OK? Doorgaan met commit? (ja/nee)"
if ($confirm1 -ne "ja") {
    Write-Host "Gestopt. Pas je .gitignore aan en run 'git reset <bestand>' om iets uit staging te halen." -ForegroundColor Red
    exit
}

git commit -m "Initial import: MatchFitAI with PadelAnalysis"
Write-Host "Commit gemaakt." -ForegroundColor Green

# --- 7. Secret-scan op de staged/committed diff ---
Write-Host "`n[7/8] Laatste check op API keys / secrets in de commit..." -ForegroundColor Cyan
$found = git show --pretty="" --name-only HEAD | ForEach-Object {
    if (Test-Path $_) {
        Select-String -Path $_ -Pattern "apiKey|private_key|BEGIN PRIVATE KEY|AIza|secret" -ErrorAction SilentlyContinue
    }
}
if ($found) {
    Write-Host "  MOGELIJKE SECRETS GEVONDEN in de commit:" -ForegroundColor Red
    $found | ForEach-Object { Write-Host "    $_" -ForegroundColor Red }
    Write-Host "`n  NIET PUSHEN. Herschrijf eerst de commit (git reset --soft HEAD~1, bestand fixen/.gitignore aanvullen, opnieuw committen)." -ForegroundColor Red
    exit
} else {
    Write-Host "  Niets verdachts gevonden." -ForegroundColor Green
}

# --- 8. Remote koppelen en pushen ---
Write-Host "`n[8/8] Klaar om te pushen naar GitHub." -ForegroundColor Cyan
$repoUrl = Read-Host "Geef de HTTPS URL van de GitHub repo (bv. https://github.com/<user>/MatchFitAI.git)"
git branch -M main
if (-not (git remote | Select-String "origin")) {
    git remote add origin $repoUrl
} else {
    Write-Host "  Remote 'origin' bestaat al - controleer of dit de juiste URL is." -ForegroundColor Yellow
    git remote -v
}

$confirm2 = Read-Host "`nDoorgaan met 'git push -u origin main'? (ja/nee)"
if ($confirm2 -ne "ja") {
    Write-Host "Gestopt voor de push. Voer 'git push -u origin main' later handmatig uit." -ForegroundColor Yellow
    exit
}

git push -u origin main
Write-Host "`nKlaar! MatchFitAI is gepusht naar GitHub." -ForegroundColor Green
