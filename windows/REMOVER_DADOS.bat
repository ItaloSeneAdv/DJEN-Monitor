@echo off
chcp 65001 >nul
setlocal

title DJEN Monitor - Remover dados locais

echo ============================================================
echo  DJEN Monitor - Remoção de dados locais
echo ============================================================
echo.
echo Este procedimento remove:
echo   - agendamento automático do DJEN Monitor;
echo   - configuração e OABs cadastradas;
echo   - histórico de deduplicação;
echo   - logs e cópia interna usada pelo agendamento.
echo.
echo As planilhas em Documentos NÃO serão apagadas sem confirmação separada.
echo.
set /p CONFIRMA="Digite REMOVER para continuar: "
if /I not "%CONFIRMA%"=="REMOVER" (
    echo.
    echo Operação cancelada.
    pause
    exit /b 0
)

echo.
echo Removendo agendamento e dados locais...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='SilentlyContinue'; " ^
  "$task='DJEN Monitor - Consulta diaria'; " ^
  "Unregister-ScheduledTask -TaskName $task -Confirm:$false -ErrorAction SilentlyContinue; " ^
  "$app=Join-Path $env:LOCALAPPDATA 'DJEN Monitor'; " ^
  "if (Test-Path -LiteralPath $app) { Remove-Item -LiteralPath $app -Recurse -Force };"

if errorlevel 1 (
    echo.
    echo Não foi possível concluir toda a limpeza. Tente executar este arquivo como administrador.
    pause
    exit /b 1
)

echo.
echo Dados locais removidos.
echo.
set /p PLANILHAS="Também apagar as planilhas em Documentos\DJEN Monitor? [s/N]: "
if /I "%PLANILHAS%"=="s" goto :apagar_planilhas
if /I "%PLANILHAS%"=="sim" goto :apagar_planilhas
goto :fim

:apagar_planilhas
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "$docs=[Environment]::GetFolderPath('MyDocuments'); " ^
  "$dir=Join-Path $docs 'DJEN Monitor'; " ^
  "if (Test-Path -LiteralPath $dir) { Remove-Item -LiteralPath $dir -Recurse -Force };"
echo Planilhas removidas.

:fim
echo.
echo Limpeza concluída. Na próxima abertura o DJEN Monitor fará a configuração inicial novamente.
pause
exit /b 0
