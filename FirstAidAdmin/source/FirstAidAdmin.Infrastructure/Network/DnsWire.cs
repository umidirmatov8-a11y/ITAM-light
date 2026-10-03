using System.Buffers.Binary;
using System.Net;
using System.Text;

namespace FirstAidAdmin.Infrastructure.Network;

/// <summary>Minimal DNS message codec (RFC 1035) used to query a specific server, bypassing the OS cache.</summary>
public static class DnsWire
{
    public const ushort TypeA = 1;
    public const ushort TypeSrv = 33;

    public sealed record DnsResponse(ushort Id, int RCode, bool Truncated, int AnswerCount, IReadOnlyList<string> Addresses, IReadOnlyList<string> SrvTargets);

    public static byte[] BuildQuery(ushort id, string name, ushort type = TypeA)
    {
        var buf = new List<byte>(64);
        void U16(ushort v) { buf.Add((byte)(v >> 8)); buf.Add((byte)v); }
        U16(id);
        U16(0x0100); // standard query, recursion desired
        U16(1); U16(0); U16(0); U16(0);
        foreach (var label in name.TrimEnd('.').Split('.', StringSplitOptions.RemoveEmptyEntries))
        {
            var bytes = Encoding.ASCII.GetBytes(label);
            if (bytes.Length > 63) throw new ArgumentException("DNS label too long", nameof(name));
            buf.Add((byte)bytes.Length);
            buf.AddRange(bytes);
        }
        buf.Add(0);
        U16(type);
        U16(1); // IN
        return buf.ToArray();
    }

    public static DnsResponse Parse(ReadOnlySpan<byte> msg)
    {
        if (msg.Length < 12) throw new FormatException("DNS response too short");
        var id = BinaryPrimitives.ReadUInt16BigEndian(msg);
        var flags = BinaryPrimitives.ReadUInt16BigEndian(msg[2..]);
        var qd = BinaryPrimitives.ReadUInt16BigEndian(msg[4..]);
        var an = BinaryPrimitives.ReadUInt16BigEndian(msg[6..]);
        var rcode = flags & 0x000F;
        var tc = (flags & 0x0200) != 0;
        var pos = 12;
        for (var i = 0; i < qd; i++)
        {
            pos = SkipName(msg, pos);
            pos += 4;
        }
        var addresses = new List<string>();
        var srv = new List<string>();
        for (var i = 0; i < an && pos < msg.Length; i++)
        {
            pos = SkipName(msg, pos);
            if (pos + 10 > msg.Length) break;
            var type = BinaryPrimitives.ReadUInt16BigEndian(msg[pos..]);
            var rdlen = BinaryPrimitives.ReadUInt16BigEndian(msg[(pos + 8)..]);
            pos += 10;
            if (pos + rdlen > msg.Length) break;
            if (type == TypeA && rdlen == 4)
                addresses.Add(new IPAddress(msg.Slice(pos, 4)).ToString());
            else if (type == 28 && rdlen == 16)
                addresses.Add(new IPAddress(msg.Slice(pos, 16)).ToString());
            else if (type == TypeSrv && rdlen > 6)
                srv.Add(ReadName(msg, pos + 6) + ":" + BinaryPrimitives.ReadUInt16BigEndian(msg[(pos + 4)..]));
            pos += rdlen;
        }
        return new DnsResponse(id, rcode, tc, an, addresses, srv);
    }

    private static int SkipName(ReadOnlySpan<byte> msg, int pos)
    {
        while (pos < msg.Length)
        {
            var len = msg[pos];
            if (len == 0) return pos + 1;
            if ((len & 0xC0) == 0xC0) return pos + 2;
            pos += len + 1;
        }
        throw new FormatException("Malformed DNS name");
    }

    private static string ReadName(ReadOnlySpan<byte> msg, int pos)
    {
        var sb = new StringBuilder();
        var jumps = 0;
        while (pos < msg.Length && jumps < 20)
        {
            var len = msg[pos];
            if (len == 0) break;
            if ((len & 0xC0) == 0xC0)
            {
                pos = ((len & 0x3F) << 8) | msg[pos + 1];
                jumps++;
                continue;
            }
            if (sb.Length > 0) sb.Append('.');
            sb.Append(Encoding.ASCII.GetString(msg.Slice(pos + 1, len)));
            pos += len + 1;
        }
        return sb.ToString();
    }

    public static string RCodeText(int rcode) => rcode switch
    {
        0 => "NOERROR",
        1 => "FORMERR",
        2 => "SERVFAIL",
        3 => "NXDOMAIN",
        4 => "NOTIMP",
        5 => "REFUSED",
        _ => "RCODE " + rcode
    };
}
