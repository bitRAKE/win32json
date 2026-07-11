; Selective type: Networking.WinSock.WSAData
; Generated from marlersoft/win32json. Do not edit by hand.
; Target architecture: x64
; struct WSAData (Networking.WinSock), sizeof=408, align=8
struct WSAData
?wVersion dw ? ; offset 0, UInt16
?wHighVersion dw ? ; offset 2, UInt16
?iMaxSockets dw ? ; offset 4, UInt16
?iMaxUdpDg dw ? ; offset 6, UInt16
?lpVendorInfo dq ? ; offset 8, pointer
?szDescription db 257 dup (?) ; offset 16, 257 x Byte
?szSystemStatus db 129 dup (?) ; offset 273, 129 x Byte
db 6 dup (?) ; tail padding
ends
