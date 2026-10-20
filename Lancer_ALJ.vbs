Set FSO = CreateObject("Scripting.FileSystemObject") 
scriptPath = FSO.GetParentFolderName(WScript.ScriptFullName) 
Set WshShell = CreateObject("WScript.Shell") 
WshShell.CurrentDirectory = scriptPath & "\code_source\scripts" 
WshShell.Run "cmd.exe /c run_app.bat", 0, False 
