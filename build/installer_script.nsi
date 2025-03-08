!define APP_NAME "Finance Analysis"
!define APP_VERSION "1.0.0"
!define OUTPUT_EXE "FinanceAppInstaller.exe"

OutFile "${OUTPUT_EXE}"
InstallDir "$PROGRAMFILES\${APP_NAME}"
InstallDirRegKey HKLM "Software\${APP_NAME}" "Install_Dir"
RequestExecutionLevel admin

SetCompress auto
SetCompressor lzma
CRCCheck on
XPStyle on
Name "${APP_NAME} ${APP_VERSION}"
BrandingText "Installer for ${APP_NAME}"

Icon "..\icon.ico"
!include "MUI2.nsh"

Var StartMenuFolder
Var DesktopShortcut

;--------------------------------
; Pages
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

;--------------------------------
; Languages
!insertmacro MUI_LANGUAGE "English"

;--------------------------------
; Installer Section

Section "Install"

  SetOutPath "$INSTDIR"

  ; Copy all app files
  File /r "..\dist\*.*"

  ; Save install path in registry
  WriteRegStr HKLM "Software\${APP_NAME}" "Install_Dir" "$INSTDIR"

  ; Register uninstall info
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "DisplayName" "${APP_NAME}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "Publisher" "Tomer Roditi"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "UninstallString" '"$INSTDIR\Uninstall.exe"'

  ; Create uninstaller
  WriteUninstaller "$INSTDIR\Uninstall.exe"

  ; Run setup script
  nsExec::ExecToLog '"$INSTDIR\build\setup.bat"'
  Pop $0
  StrCmp $0 "0" +3
    MessageBox MB_ICONEXCLAMATION "Setup script failed with exit code $0"
    Abort

  ; Create shortcuts
  CreateShortCut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\build\run.bat" "" "$INSTDIR\icon.ico"
  CreateDirectory "$SMPROGRAMS\${APP_NAME}"
  CreateShortCut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "$INSTDIR\build\run.bat" "" "$INSTDIR\icon.ico"

SectionEnd

;--------------------------------
; Uninstaller Section

Section "Uninstall"

  ; Delete files and directory
  RMDir /r "$INSTDIR"

  ; Remove shortcuts
  Delete "$DESKTOP\${APP_NAME}.lnk"
  Delete "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk"
  RMDir "$SMPROGRAMS\${APP_NAME}"

  ; Remove registry entries
  DeleteRegKey HKLM "Software\${APP_NAME}"
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}"

SectionEnd
