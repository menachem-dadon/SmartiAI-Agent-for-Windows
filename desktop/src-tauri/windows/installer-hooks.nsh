!macro NSIS_HOOK_PREINSTALL
  ; Tauri expands this macro from target/<triple>/release/nsis/<arch>.
  File /oname=$PLUGINSDIR\smarti-migrate-legacy.ps1 "${__FILEDIR__}\..\..\..\..\..\..\..\scripts\migrate_legacy_install.ps1"
  nsExec::ExecToLog 'powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$PLUGINSDIR\smarti-migrate-legacy.ps1" -Mode PreInstall'
  Pop $0
  ${If} $0 != 0
    Abort "SmartiAI could not safely back up and remove the old installation. The new installation was cancelled."
  ${EndIf}
!macroend

!macro NSIS_HOOK_POSTINSTALL
  nsExec::ExecToLog 'powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$PLUGINSDIR\smarti-migrate-legacy.ps1" -Mode PostInstall'
  Pop $0
!macroend
