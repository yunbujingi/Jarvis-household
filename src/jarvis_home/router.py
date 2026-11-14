"""Conservative fast paths; unmatched composite inputs become an encrypted draft."""
import re
from datetime import timedelta
from decimal import Decimal
from time import perf_counter

from .models import Change, today

FOODS = {"番茄", "牛奶", "鸡胸肉", "鸡蛋", "菠菜", "生菜", "西兰花", "黄瓜", "苹果", "酸奶", "豆腐", "猪肉", "牛肉", "鱼", "虾", "饺子"}
NUM = r"(?:\d+(?:\.\d+)?|[零一二两三四五六七八九十百半]+)"
CATEGORIES = {"餐饮": ("午饭", "早饭", "晚饭", "咖啡", "买菜", "外卖"), "交通": ("打车", "公交", "停车"),
              "宠物": ("猫粮", "猫砂"), "居家": ("房租", "电费", "水费"), "订阅会员": ("会员", "订阅")}


def number(value):
    if re.fullmatch(r"\d+(?:\.\d+)?", value):
        return Decimal(value)
    if value == "半":
        return Decimal("0.5")
    digits = {c:i for i,c in enumerate("零一二三四五六七八九")}
    digits["两"] = 2
    total = current = 0
    for char in value:
        if char in digits:
            current = digits[char]
        elif char in "十百":
            total += (current or 1) * (10 if char == "十" else 100)
            current = 0
        else:
            raise ValueError("数量不明确")
    result = total + current
    def canonical(n):
        chars = "零一二三四五六七八九"
        if n < 10:
            return chars[n]
        if n < 100:
            return (chars[n // 10] if n >= 20 else "") + "十" + (chars[n % 10] if n % 10 else "")
        tail = n % 100
        return chars[n // 100] + "百" + (("零" + chars[tail]) if 0 < tail < 10 else ("一" if 10 <= tail < 20 else "") + canonical(tail) if tail else "")
    if not 0 <= result < 1000 or value.replace("两", "二") != canonical(result):
        raise ValueError("数量不明确")
    return Decimal(result)


def parse(text):
    text = text.strip().rstrip("。！!")
    day = today()
    if text.startswith("昨天"):
        day -= timedelta(days=1)
        text = text[2:]
    elif text.startswith("今天"):
        text = text[2:]
    payment = "未指定"
    for suffix in ("微信", "支付宝", "现金", "信用卡"):
        if text.endswith(suffix):
            payment = suffix
            text = text[:-len(suffix)].rstrip("，, ")
            break
    changes = []
    purchase = False
    for part in re.split(r"[，,、；;]", text):
        part = part.strip()
        if not part:
            continue
        if part.startswith(("买了", "买入")):
            part, purchase = part[2:], True
        food = re.fullmatch(rf"({NUM})(个|盒|块|袋|斤|公斤|瓶|把)(.+?)(?:放(冷藏|冷冻))?", part)
        if food and purchase:
            quantity, unit, name, location = food.groups()
            if name not in FOODS:
                raise ValueError("物品需要明确存放位置")
            changes.append(Change(action="add_item", name=name, quantity=number(quantity), unit=unit,
                                  location=location or ("冷冻" if name in ("鸡胸肉", "饺子") else "冷藏"), on=day))
            continue
        location = re.fullmatch(r"(.{1,60}?)放在(.{1,80})", part)
        if location:
            changes.append(Change(action="add_item", name=location[1], quantity=1, unit="件", location=location[2], on=day))
            continue
        spent = re.fullmatch(rf"花了\s*({NUM})(?:元|块)?", part)
        if spent and changes and all(c.action == "add_item" for c in changes):
            changes.append(Change(action="expense", name="、".join(c.name for c in changes), amount=number(spent[1]), category="餐饮", payment=payment, on=day))
            continue
        expense = re.fullmatch(rf"(午饭|早饭|晚饭|咖啡|买菜|外卖|打车|公交|停车|猫粮|猫砂|房租|电费|水费|会员|订阅)\s*({NUM})(?:元|块)?", part)
        if expense:
            name, amount = expense.groups()
            category = next((k for k,v in CATEGORIES.items() if name in v), "其他")
            changes.append(Change(action="expense", name=name, amount=number(amount), category=category, payment=payment, on=day))
            continue
        raise ValueError("暂未识别完整指令")
    if not changes:
        raise ValueError("没有记录内容")
    return changes


def command(store, request_id, text):
    start = perf_counter()
    text = text.strip()
    replay = store.replay_text(request_id, text)
    if replay:
        return {**replay, "elapsed_ms": round((perf_counter() - start) * 1000, 2), "route": "local", "model_calls": 0}
    if text in ("撤销", "撤销上一笔", "删掉上一笔", "刚才那条删掉"):
        result = store.execute(request_id, text=text, undo=True)
    elif re.fullmatch(r"(.{1,100})在哪[？?]?", text):
        name = re.fullmatch(r"(.{1,100})在哪[？?]?", text)[1]
        items = [i for i in store.snapshot()["items"] if i["name"] == name]
        result = {"status": "completed", "records": [], "request_id": request_id,
                  "message": "；".join(f"{i['name']}在{i['location']}（记录于{i['on']}）" for i in items[:3]) or "还没有这件物品的记录。"}
    elif re.fullmatch(rf"(?:拿了|用了)({NUM})(个|盒|块|袋|斤|公斤|瓶|把)(.+)", text):
        match = re.fullmatch(rf"(?:拿了|用了)({NUM})(个|盒|块|袋|斤|公斤|瓶|把)(.+)", text)
        items = [i for i in store.snapshot()["items"] if i["name"] == match[3]]
        if len(items) != 1:
            result = store.execute(request_id, text=text, draft=True)
        else:
            item = items[0]
            result = store.execute(request_id, [Change(action="consume", name=item["name"], record_id=item["id"],
                quantity=number(match[1]), unit=match[2], expected_version=item["version"])], text=text)
    elif text in ("冰箱里有什么", "冰箱里有什么？", "库存", "物品在哪", "这个月花了多少", "这个月花了多少？"):
        snap = store.snapshot()
        if "花了" in text:
            message = f"本月净支出 {Decimal(snap['net_spend_cents']) / 100:.2f} 元。"
        else:
            items = snap["items"]
            if text.startswith("冰箱"):
                items = [i for i in items if i["location"] in ("冷藏", "冷冻")]
            message = "；".join(f"{i['name']} {i['quantity']}{i['unit']}，{i['location']}" for i in items[:3]) or "还没有物品记录。"
            if len(items) > 3:
                message += f"；另有 {len(items)-3} 项可在页面查看。"
        result = {"status": "completed", "message": message, "records": [], "request_id": request_id}
    else:
        try:
            changes = parse(text)
        except ValueError:
            result = store.execute(request_id, text=text, draft=True)
        else:
            result = store.execute(request_id, changes, text=text)
    return {**result, "elapsed_ms": round((perf_counter() - start) * 1000, 2), "route": "local", "model_calls": 0}
