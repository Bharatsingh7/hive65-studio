Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;
public static class H {
  [StructLayout(LayoutKind.Sequential)] public struct CAPS {
    public ushort Usage, UsagePage, In, Out, Feat;
    [MarshalAs(UnmanagedType.ByValArray, SizeConst=17)] public ushort[] R;
    public ushort a,b,c,d,e,f,g,h,i,j; }
  [DllImport("kernel32.dll", SetLastError=true, CharSet=CharSet.Unicode)]
  public static extern SafeFileHandle CreateFile(string n, uint acc, uint share, IntPtr sa, uint disp, uint fl, IntPtr t);
  [DllImport("hid.dll")] public static extern bool HidD_GetPreparsedData(SafeFileHandle h, out IntPtr p);
  [DllImport("hid.dll")] public static extern bool HidD_FreePreparsedData(IntPtr p);
  [DllImport("hid.dll")] public static extern int HidP_GetCaps(IntPtr p, out CAPS c);
}
'@
Get-PnpDevice -PresentOnly -Class HIDClass | Where-Object InstanceId -match 'VID_258A&PID_010C' | ForEach-Object {
  $iface = (Get-PnpDeviceProperty -InstanceId $_.InstanceId -KeyName 'DEVPKEY_Device_InstanceId').Data
  $path = '\\?\' + ($_.InstanceId -replace '\\','#') + '#{4d1e55b2-f16f-11cf-88cb-001111000030}'
  $h = [H]::CreateFile($path, 0, 3, [IntPtr]::Zero, 3, 0, [IntPtr]::Zero)
  if ($h.IsInvalid) { "{0}: open failed" -f $_.InstanceId; return }
  $p=[IntPtr]::Zero; [void][H]::HidD_GetPreparsedData($h,[ref]$p)
  $c=New-Object H+CAPS; [void][H]::HidP_GetCaps($p,[ref]$c); [void][H]::HidD_FreePreparsedData($p); $h.Close()
  "{0,-50} page=0x{1:X4} usage=0x{2:X2} in={3} out={4} feat={5}" -f ($_.InstanceId -replace '\\7&.*',''), $c.UsagePage, $c.Usage, $c.In, $c.Out, $c.Feat
}
