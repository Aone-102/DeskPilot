Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' Current directory of this script
ScriptDir = fso.GetParentFolderName(WScript.ScriptFullName)

' Find Pythonw path
PythonwPath = "C:\Users\cheon\AppData\Local\Programs\Python\Python312\pythonw.exe"

If Not fso.FileExists(PythonwPath) Then
    PythonwPath = "pythonw.exe"
End If

' Pass arguments
Args = ""
For i = 0 To WScript.Arguments.Count - 1
    Args = Args & " " & WScript.Arguments(i)
Next

Cmd = """" & PythonwPath & """ """ & ScriptDir & "\app.py""" & Args
WshShell.CurrentDirectory = ScriptDir
WshShell.Run Cmd, 0, False
