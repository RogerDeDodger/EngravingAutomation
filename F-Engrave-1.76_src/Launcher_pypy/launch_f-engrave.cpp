#include "pch.h"
#include <iostream>
#include <atlstr.h>
#include <stdio.h>
#include <strsafe.h>

int main(int argc, char *argv[])
{
	LPSTR path    = new CHAR[MAX_PATH];
	LPSTR cmd_line = new CHAR[MAX_PATH];
	LPSTR run_directory = new CHAR[MAX_PATH];

	/* Set the paths */
	//strcpy_s(path, MAX_PATH, "C:\\temp\\F-Engrave\\pypy\\pypy3.exe");
	//strcpy_s(run_directory, MAX_PATH, "C:\\temp\\F-Engrave\\run\\");
	strcpy_s(path, MAX_PATH, ".\\pypy\\pypy3.exe");
	//strcpy_s(run_directory, MAX_PATH, ".\\run\\");
	strcpy_s(run_directory, MAX_PATH, ".\\");

	/* Set the command */
	//strcpy_s(cmd_line, MAX_PATH, " f-engrave.py");
	strcpy_s(cmd_line, MAX_PATH, " source.py");

	for (int i = 1; i < argc; i++)
	{
		strcat_s(cmd_line, MAX_PATH, " \"");
		strcat_s(cmd_line, MAX_PATH, argv[i]);
		strcat_s(cmd_line, MAX_PATH, "\"");
	}

	// Set up the structures
	STARTUPINFOA si;
	PROCESS_INFORMATION pi;
	ZeroMemory(&si, sizeof(si));
	si.cb = sizeof(si);
	ZeroMemory(&pi, sizeof(pi));

	
	int console = CREATE_NO_WINDOW;
    if (argc > 1) console = 0; // Attached to current console
	bool result = CreateProcessA
	(
		path,               // Path to execuable
		cmd_line,              // cmd_line line options
		NULL,               // Process handle not inheritable
		NULL,               // Thread handle not inheritable
		FALSE,              // Set handle inheritance to FALSE
		console,            // NULL, 0, CREATE_NO_WINDOW, DETACHED_PROCESS, CREATE_NEW_CONSOLE, // Opens file in a separate console
		NULL,               // Use parent's environment block
		run_directory,      // directory 
		&si,                // Pointer to STARTUPINFO structure
		&pi                 // Pointer to PROCESS_INFORMATION structure
	);

	if (!result)         printf("F-Engrave Failed to start. cmd_line=\"%s %s\"\n", path, cmd_line);
	else if (console==0) WaitForSingleObject(pi.hProcess, INFINITE);

	// Close process and thread handles.
	CloseHandle(pi.hProcess);
	CloseHandle(pi.hThread);
	delete[] path;
	delete[] cmd_line;
}

