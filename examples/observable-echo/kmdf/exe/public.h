/*++
Copyright (c) 1990-2000    Microsoft Corporation All Rights Reserved

Module Name:

    public.h

Abstract:

    This module contains the common declarations shared by driver
    and user applications.


Environment:

    user and kernel

--*/

#define WHILE(a) \
__pragma(warning(suppress:4127)) while(a)

//
// Define an Interface Guid so that app can find the device and talk to it.
//

DEFINE_GUID (GUID_DEVINTERFACE_ECHO,
    0xcdc35b6e, 0xbe4, 0x4936, 0xbf, 0x5f, 0x55, 0x37, 0x38, 0xa, 0x7c, 0x1a);
// {CDC35B6E-0BE4-4936-BF5F-5537380A7C1A}


// Lab-only bounded computation: no pointers, addresses, or arbitrary memory access.
#define IOCTL_WKL_PROBE CTL_CODE(FILE_DEVICE_UNKNOWN, 0x800, METHOD_BUFFERED, FILE_READ_DATA | FILE_WRITE_DATA)
#define WKL_PROBE_VERSION 1UL
#define WKL_PROBE_BUILD 0x20261118UL
#define WKL_PROBE_XOR 0x574B4C5F50524F42ULL

typedef struct _WKL_PROBE_REQUEST {
    ULONG Version;
    ULONG Reserved;
    ULONG64 Input;
} WKL_PROBE_REQUEST, *PWKL_PROBE_REQUEST;

typedef struct _WKL_PROBE_RESPONSE {
    ULONG Version;
    ULONG Build;
    ULONG64 Input;
    ULONG64 Output;
    ULONG Calls;
    ULONG Reserved;
} WKL_PROBE_RESPONSE, *PWKL_PROBE_RESPONSE;
