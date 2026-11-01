#include <windows.h>
WINBASEAPI UINT WINAPI MultiByteToWideChar(UINT,DWORD,LPCSTR,int,LPWSTR,int);
WINBASEAPI int WINAPI WideCharToMultiByte(UINT,DWORD,LPCWSTR,int,LPSTR,int,LPCSTR,LPBOOL);
static __inline ULONGLONG GetTickCount64(void){return (ULONGLONG)GetTickCount();}
#ifndef CP_UTF8
#define CP_UTF8 65001
#endif
#ifndef CP_ACP
#define CP_ACP 0
#endif
#ifndef MB_ERR_INVALID_CHARS
#define MB_ERR_INVALID_CHARS 0x00000008
#endif
#ifndef CP_OEMCP
#define CP_OEMCP 1
#endif
