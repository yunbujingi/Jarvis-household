"""Generate repository diagrams as SVG and PNG; no network or private data."""
import html
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs' / 'images'
FONT_CANDIDATES = [os.environ.get('JWS_DIAGRAM_FONT', ''),
    '/System/Library/Fonts/PingFang.ttc',
    '/System/Library/Fonts/STHeiti Light.ttc',
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc']
FONT = next((p for p in FONT_CANDIDATES if p and Path(p).is_file()), None)
if FONT is None:
    raise SystemExit('Set JWS_DIAGRAM_FONT to a Chinese-capable font file.')

INK, MUTED, BLUE, GREEN, LINE = '#152b40', '#506579', '#2468d3', '#087d70', '#8b9bae'


class Canvas:
    def __init__(self, height):
        self.width, self.height = 1600, height
        self.image = Image.new('RGB', (self.width, height), '#f4f7fb')
        self.draw = ImageDraw.Draw(self.image)
        self.svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="{height}" viewBox="0 0 1600 {height}" role="img">',
                    '<rect width="100%" height="100%" fill="#f4f7fb"/>']

    def text(self, x, y, text, size=24, color=INK):
        self.draw.text((x, y), text, font=ImageFont.truetype(FONT, size), fill=color, anchor='lt')
        self.svg.append(f'<text x="{x}" y="{y + size}" font-family="PingFang SC,Noto Sans CJK SC,sans-serif" font-size="{size}" fill="{color}">{html.escape(text)}</text>')

    def box(self, x, y, w, h, title, lines=(), tint='white', border='#d6e0eb', title_color=INK):
        self.draw.rounded_rectangle((x, y, x+w, y+h), radius=20, fill=tint, outline=border, width=2)
        self.svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="20" fill="{tint}" stroke="{border}" stroke-width="2"/>')
        if title:
            self.text(x+24, y+22, title, 28, title_color)
        for i, line in enumerate(lines):
            self.text(x+24, y+69+i*34, line, 22, MUTED)

    def line(self, points, color=LINE, width=3, arrow=False, both=False, dashed=False):
        if dashed:
            # All dashed guides in these diagrams are vertical.
            (x, y), (_, end) = points
            for start in range(y, end, 14):
                self.draw.line((x, start, x, min(start+7, end)), fill=color, width=width)
        else:
            self.draw.line(points, fill=color, width=width)
        coords = ' '.join(f'{x},{y}' for x, y in points)
        dash = ' stroke-dasharray="7 7"' if dashed else ''
        self.svg.append(f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="{width}"{dash}/>')
        def head(a, b):
            import math
            angle = math.atan2(b[1]-a[1], b[0]-a[0])
            pts = [b, (b[0]-14*math.cos(angle-.48), b[1]-14*math.sin(angle-.48)),
                   (b[0]-14*math.cos(angle+.48), b[1]-14*math.sin(angle+.48))]
            self.draw.polygon(pts, fill=color)
            self.svg.append('<polygon points="'+' '.join(f'{x},{y}' for x,y in pts)+f'" fill="{color}"/>')
        if arrow:
            head(points[-2], points[-1])
        if both:
            head(points[1], points[0])

    def save(self, name):
        OUT.mkdir(parents=True, exist_ok=True)
        self.image.save(OUT / f'{name}.png', optimize=True)
        (OUT / f'{name}.svg').write_text('\n'.join(self.svg+['</svg>']))


def topology():
    c = Canvas(1130)
    c.text(60, 42, 'JWS 家庭助手 · 连接拓扑', 44)
    c.text(62, 103, '家庭共享账本 · 无成员身份鉴别 · 保留现有语音与家居体验。', 25, MUTED)
    c.box(60, 180, 350, 155, '小智硬件', ['收音 · 播放 · 设备交互'])
    c.box(570, 170, 570, 175, '官方小智', ['现有语音服务与模型', '理解指令 · 选择工具 · 组织回答'], '#edf3ff', '#a9c4ef', BLUE)
    c.line([(410, 255),(570, 255)], BLUE, arrow=True, both=True)
    c.text(430, 212, '语音链路', 22, BLUE)
    c.box(60, 430, 990, 355, 'NAS / 独立主机', tint='#eef8f5', border='#add7cc', title_color=GREEN)
    c.box(90, 520, 290, 155, 'JWS 出站桥', ['凭据隔离 / 脱敏耗时', '只转发三个账本工具'])
    c.box(425, 520, 270, 155, 'MCP 工具', ['记录 · 查询 · 撤销', '入库纠错 / 版本检查'])
    c.box(740, 520, 280, 155, '加密账本', ['SQLite / 事务 / 审计', '校验备份 / 独立恢复'])
    c.line([(380, 598),(425, 598)], GREEN, arrow=True, both=True)
    c.line([(695, 598),(740, 598)], GREEN, arrow=True, both=True)
    c.line([(340, 520),(340, 390),(820, 390),(820, 345)], GREEN, arrow=True, both=True)
    c.text(374, 356, 'NAS 主动建立 WSS；无需公网应用端口', 22, GREEN)
    c.text(94, 714, '本仓库的运行范围  /  不持有 HA 或小佩账户凭据', 24, GREEN)
    c.box(1140, 435, 400, 145, '既有 Home Assistant', ['原家居工具桥', '独立配置与运行'])
    c.box(1140, 645, 400, 145, '既有猫咪管家', ['原宠物工具桥', '独立部署与设备安全规则'])
    c.line([(1140, 255),(1340, 255),(1340, 435)], BLUE, arrow=True, both=True)
    c.line([(1500, 645),(1570, 645),(1570, 310),(1140, 310)], BLUE, arrow=True, both=True)
    c.text(1176, 370, '外部集成 / 不包含其源码', 21, MUTED)
    c.box(60, 845, 1480, 215, '', tint='#fff8ed', border='#e4cda6')
    c.text(90, 870, '本机预览 · 独立数据源', 28, '#91621c')
    c.box(95, 925, 350, 92, '浏览器文字入口', tint='white')
    c.box(615, 925, 400, 92, '本机账本 / 回环 HTTP', tint='white')
    c.line([(445, 970),(615, 970)], '#91621c', arrow=True, both=True)
    c.text(1070, 935, '不与 NAS 自动同步', 24, '#91621c')
    c.text(1070, 975, '不提供远程成员认证', 22, MUTED)
    c.text(62, 1087, '箭头表示数据流；官方模型可见被调用工具的参数与结果。', 20, MUTED)
    c.save('topology')


def request_flow():
    c = Canvas(1110)
    c.text(60, 42, '一句话如何变成真实记录', 44)
    c.text(62, 103, '典型单次工具调用；JWS 不额外调用语言模型。', 25, MUTED)
    centers = [195, 595, 995, 1395]
    titles = ['用户 / 硬件','官方小智','JWS 出站桥','MCP / 账本']
    for x, title in zip(centers, titles):
        c.box(x-155, 175, 310, 90, title)
        c.line([(x, 280),(x, 900)], '#c5d0de', 2, dashed=True)
    steps = [
        (0,1,330,'① 语音或明确指令',BLUE),
        (1,2,430,'② tools/call + 参数',BLUE),
        (2,3,530,'③ 限时转发 / stdio',GREEN),
        (3,2,720,'⑤ 真实结果 / 明确错误',GREEN),
        (2,1,800,'⑥ 返回工具结果',BLUE),
        (1,0,880,'⑦ 简短语音回答',BLUE),
    ]
    for a,b,y,label,color in steps:
        c.line([(centers[a],y),(centers[b],y)],color,arrow=True)
        c.text(min(centers[a],centers[b])+35,y-42,label,23,color)
    c.box(1130, 580, 425, 95, '④ 版本检查 / 原子事务', ['纠错、审计与幂等结果同提交'], '#eef8f5', '#add7cc', GREEN)
    c.box(60, 955, 1480, 100, '', tint='#edf3ff', border='#c7d8f3')
    c.text(90, 979, '更短的回答：服务端筛选 → 建议 3 条以内 → 按需继续查询', 27, BLUE)
    c.text(90, 1020, '超时 / 取消 / 断线均可能已提交；重连不自动回放，同一 request_id 重试取原结果。', 21, MUTED)
    c.save('request-flow')


if __name__ == '__main__':
    topology()
    request_flow()
    print('Generated topology and request-flow (SVG + PNG).')
