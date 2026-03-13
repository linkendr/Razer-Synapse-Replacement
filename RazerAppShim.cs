using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text;

internal static class Program
{
    private static int Main(string[] args)
    {
        try
        {
            var root = AppDomain.CurrentDomain.BaseDirectory;
            var logPath = Path.Combine(root, "razer-app-shim.log");
            var exePath = Process.GetCurrentProcess().MainModule.FileName;
            var escapedArgs = string.Join(", ", args.Select(a => "\"" + Escape(a) + "\""));
            var builder = new StringBuilder();
            builder.AppendLine("{");
            builder.Append("  \"timestamp\": \"").Append(Escape(DateTimeOffset.Now.ToString("O"))).AppendLine("\",");
            builder.Append("  \"exe\": \"").Append(Escape(exePath ?? string.Empty)).AppendLine("\",");
            builder.Append("  \"cwd\": \"").Append(Escape(Environment.CurrentDirectory)).AppendLine("\",");
            builder.Append("  \"args\": [").Append(escapedArgs).AppendLine("]");
            builder.AppendLine("}");
            File.AppendAllText(logPath, builder.ToString(), Encoding.UTF8);
            return 0;
        }
        catch
        {
            return 1;
        }
    }

    private static string Escape(string value)
    {
        return value.Replace("\\", "\\\\").Replace("\"", "\\\"");
    }
}
