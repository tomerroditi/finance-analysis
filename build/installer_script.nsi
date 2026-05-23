; Finance Analysis — Windows installer.
;
; Per-user install at $LOCALAPPDATA\Programs\Finance Analysis (no admin).
; Source layout: PyInstaller has produced dist/FinanceAnalysis/, a
; self-contained directory with FinanceAnalysis.exe + _internal/.
; This installer drops that tree into $INSTDIR and registers the
; standard Add/Remove Programs metadata. There is no setup.bat, no
; .venv, no Python/Node bootstrap — the bundled exe contains everything.
;
; Uninstaller offers an opt-in "also delete my data + saved passwords"
; component that delegates to FinanceAnalysis.exe --uninstall-cleanup,
; reusing the same backend.uninstall.cleanup module the macOS
; uninstall.command and the in-app uninstall route use. Single source
; of truth for "what counts as Finance Analysis state on this machine".

!define APP_NAME "Finance Analysis"
!define APP_VERSION "1.22.0"
!define APP_PUBLISHER "Tomer Roditi"
!define APP_URL "https://github.com/tomerroditi/finance-analysis"
!define OUTPUT_EXE "FinanceAppInstaller.exe"
!define UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}"
!define APP_REG_KEY "Software\${APP_NAME}"

OutFile "${OUTPUT_EXE}"
InstallDir "$LOCALAPPDATA\Programs\${APP_NAME}"
InstallDirRegKey HKCU "${APP_REG_KEY}" "InstallDir"

; Per-user install: no admin elevation, no UAC prompt for the user, and
; the in-INSTDIR .venv lives somewhere we can write to without ACL pain.
RequestExecutionLevel user

SetCompress auto
SetCompressor lzma
CRCCheck on
XPStyle on
Unicode true
Name "${APP_NAME} ${APP_VERSION}"
BrandingText "Installer for ${APP_NAME}"

; ``Icon`` is the icon shown for FinanceAppInstaller.exe itself in
; Explorer + the installer window's title bar. ``UninstallIcon`` is
; the icon for Uninstall.exe (Add/Remove Programs reads this when
; rendering its own list of "uninstall this app" entries — without
; it, the entry shows the generic NSIS uninstaller icon).
Icon "..\icon.ico"
UninstallIcon "..\icon.ico"
!include "MUI2.nsh"
!include "FileFunc.nsh"
!include "LogicLib.nsh"

;--------------------------------
; Pages

!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
; Uninstall pages: components page lets the user opt in to data wipe.
!insertmacro MUI_UNPAGE_COMPONENTS
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

;--------------------------------
; Languages
!insertmacro MUI_LANGUAGE "English"

;--------------------------------
; Pre-install: detect previous installs and remove them cleanly.

Function .onInit
  ; --- Existing per-user install (HKCU)? Silent-uninstall it. ---
  ReadRegStr $0 HKCU "${APP_REG_KEY}" "InstallDir"
  ${If} $0 != ""
  ${AndIf} ${FileExists} "$0\Uninstall.exe"
    DetailPrint "Removing previous install at $0..."
    ; ``_?=$0`` keeps Uninstall.exe in-process so we can wait for it.
    ExecWait '"$0\Uninstall.exe" /S _?=$0' $1
    ; The uninstaller leaves itself behind when ``_?=`` is set; clean it up.
    Delete "$0\Uninstall.exe"
    RMDir /r "$0"
  ${EndIf}

  ; --- Legacy HKLM install (Program Files, admin)? Offer migration. ---
  ReadRegStr $0 HKLM "Software\${APP_NAME}" "Install_Dir"
  ${If} $0 != ""
  ${AndIf} ${FileExists} "$0\Uninstall.exe"
    MessageBox MB_YESNO|MB_ICONQUESTION \
      "An older system-wide install of ${APP_NAME} was found at:$\r$\n$0$\r$\n$\r$\nThe new installer is per-user and does not require administrator rights. Migrate now?$\r$\n$\r$\nYour data in %USERPROFILE%\.finance-analysis\ will not be touched." \
      IDYES legacy_migrate IDNO legacy_skip
    legacy_migrate:
      DetailPrint "Removing legacy system-wide install at $0..."
      ; Legacy uninstaller required admin; ExecShellWait uses runas so
      ; the UAC prompt fires for the legacy uninstaller only.
      ExecShellWait "" '"$0\Uninstall.exe"' "/S _?=$0"
      Goto legacy_done
    legacy_skip:
      Abort "Installation aborted at user request."
    legacy_done:
  ${EndIf}
FunctionEnd

;--------------------------------
; Installer Section

Section "Install"

  SetOutPath "$INSTDIR"

  ; Copy the PyInstaller-produced self-contained directory into $INSTDIR.
  ; Layout under ..\dist\FinanceAnalysis\:
  ;   FinanceAnalysis.exe
  ;   _internal\        (Python interpreter, deps, frontend/dist, Chromium)
  File /r "..\dist\FinanceAnalysis\*.*"

  ; Save install path in registry (HKCU — per-user install)
  WriteRegStr HKCU "${APP_REG_KEY}" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "${APP_REG_KEY}" "Version"    "${APP_VERSION}"

  ; Add/Remove Programs entry (per-user)
  WriteRegStr   HKCU "${UNINST_KEY}" "DisplayName"          "${APP_NAME}"
  WriteRegStr   HKCU "${UNINST_KEY}" "DisplayVersion"       "${APP_VERSION}"
  WriteRegStr   HKCU "${UNINST_KEY}" "Publisher"            "${APP_PUBLISHER}"
  WriteRegStr   HKCU "${UNINST_KEY}" "DisplayIcon"          "$INSTDIR\FinanceAnalysis.exe"
  WriteRegStr   HKCU "${UNINST_KEY}" "InstallLocation"      "$INSTDIR"
  WriteRegStr   HKCU "${UNINST_KEY}" "UninstallString"      '"$INSTDIR\Uninstall.exe"'
  WriteRegStr   HKCU "${UNINST_KEY}" "QuietUninstallString" '"$INSTDIR\Uninstall.exe" /S'
  WriteRegStr   HKCU "${UNINST_KEY}" "URLInfoAbout"         "${APP_URL}"
  WriteRegStr   HKCU "${UNINST_KEY}" "URLUpdateInfo"        "${APP_URL}/releases"
  WriteRegStr   HKCU "${UNINST_KEY}" "HelpLink"             "${APP_URL}"
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoModify"             1
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoRepair"             1

  WriteUninstaller "$INSTDIR\Uninstall.exe"

  ; EstimatedSize for Add/Remove Programs (KB). Computed AFTER the file
  ; copy so the bundled Chromium / Python / dependencies are included.
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  WriteRegDWORD HKCU "${UNINST_KEY}" "EstimatedSize" $0

  ; Create shortcuts directly to the bundled exe — no batch wrapper.
  CreateShortCut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\FinanceAnalysis.exe" "" "$INSTDIR\FinanceAnalysis.exe"
  CreateDirectory "$SMPROGRAMS\${APP_NAME}"
  CreateShortCut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "$INSTDIR\FinanceAnalysis.exe" "" "$INSTDIR\FinanceAnalysis.exe"

SectionEnd

;--------------------------------
; Uninstaller — components page lets the user opt in to a full data wipe.
;
; Section names in the uninstaller MUST be prefixed with "un." for NSIS
; to recognise them as uninstall sections. The "-" prefix on the core
; section hides it from the user-visible components list (we don't want
; a "uninstall the program (yes/no)" checkbox — that's redundant with
; clicking Uninstall in the first place). The optional wipe section is
; declared with /o so it starts unchecked.

; Optional opt-in: also wipe the user-data dir + Keychain entries.
; This is just a marker section — the real deletion runs inside the
; core section so it can use the venv-hosted Python interpreter
; *before* $INSTDIR is deleted.
Section /o "un.Also delete my data and saved passwords" UninstallWipeData
SectionEnd

; Required core uninstall: kill running processes, run the cleanup CLI
; (Keychain only, or Keychain + user-data per the optional section),
; then remove shortcuts, install dir, registry entries.
Section "-un.Uninstall (binaries)" UninstallCore
  ; Best-effort: stop the bundled exe before we try to delete the
  ; directory. ``taskkill`` returns non-zero when no matching process is
  ; found; we ignore that and move on.
  nsExec::ExecToLog 'taskkill /F /IM "FinanceAnalysis.exe"'
  Pop $0

  ; Delegate Keychain / user-data cleanup to the bundled binary's
  ; --uninstall-cleanup mode. This is the single source of truth shared
  ; with the macOS uninstall.command and the in-app uninstall route.
  ; MUST run before we delete $INSTDIR (which contains the exe itself).
  ${If} ${SectionIsSelected} ${UninstallWipeData}
    DetailPrint "Removing user data and saved passwords..."
    nsExec::ExecToLog '"$INSTDIR\FinanceAnalysis.exe" --uninstall-cleanup --wipe'
    Pop $0
  ${Else}
    DetailPrint "Removing Keychain entries (preserving data)..."
    nsExec::ExecToLog '"$INSTDIR\FinanceAnalysis.exe" --uninstall-cleanup --keep-data'
    Pop $0
  ${EndIf}

  ; Remove shortcuts.
  Delete "$DESKTOP\${APP_NAME}.lnk"
  Delete "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk"
  RMDir  "$SMPROGRAMS\${APP_NAME}"

  ; Remove install dir (the entire PyInstaller bundle directory).
  RMDir /r "$INSTDIR"

  ; Remove registry entries.
  DeleteRegKey HKCU "${APP_REG_KEY}"
  DeleteRegKey HKCU "${UNINST_KEY}"
SectionEnd

LangString DESC_UninstallWipeData ${LANG_ENGLISH} "Permanently delete your transactions database, credentials YAML, and Windows Credential Manager entries. Cannot be undone."

!insertmacro MUI_UNFUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${UninstallWipeData} $(DESC_UninstallWipeData)
!insertmacro MUI_UNFUNCTION_DESCRIPTION_END
