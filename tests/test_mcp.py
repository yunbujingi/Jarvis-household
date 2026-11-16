import asyncio
import json
import os
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def test_real_stdio_handshake_record_query_undo(tmp_path):
    async def run():
        env={**os.environ,'JWS_DATA_DIR':str(tmp_path/'mcp')}
        params=StdioServerParameters(command=sys.executable,args=['-m','jarvis_home.mcp'],env=env)
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write) as client:
                await client.initialize()
                tools=await client.list_tools()
                assert {t.name for t in tools.tools}=={'household_query','household_record','household_undo'}
                result=await client.call_tool('household_record',{'request_id':'mcp-test-0001','changes':[{'action':'expense','name':'测试账目','amount':'0.10'}]})
                assert not result.isError
                query=await client.call_tool('household_query',{})
                assert json.loads(query.content[0].text)['net_spend_cents']==10
                inventory=await client.call_tool('household_query',{'scope':'items'})
                assert 'net_spend_cents' not in json.loads(inventory.content[0].text)
                duplicate=await client.call_tool('household_record',{'request_id':'mcp-test-0001','changes':[{'action':'expense','name':'测试账目','amount':'0.10'}]})
                assert json.loads(duplicate.content[0].text)['replayed']
                await client.call_tool('household_undo',{'request_id':'mcp-test-0002'})
                query=await client.call_tool('household_query',{})
                assert json.loads(query.content[0].text)['net_spend_cents']==0
                item = await client.call_tool('household_record', {'request_id':'mcp-items-0001', 'changes':[
                    {'action':'add_item','name':'验收牛奶','quantity':2,'unit':'盒','location':'冰箱冷藏上层','due':'2026-11-22'},
                    {'action':'add_item','name':'验收电池','quantity':4,'unit':'节','location':'书房抽屉'}]})
                assert not item.isError
                result = await client.call_tool('household_query', {'scope':'items','name':'验收牛奶','location':'冷藏','limit':3})
                rows = json.loads(result.content[0].text)
                assert rows['item_count'] == 1 and rows['records'][0]['due'] == '2026-11-22'
                assert 'net_spend_cents' not in rows
                unknown = await client.call_tool('household_query', {'scope':'items','expiry':'unset'})
                assert json.loads(unknown.content[0].text)['records'][0]['name'] == '验收电池'
                invalid = await client.call_tool('household_query', {'scope':'expenses','name':'牛奶'})
                assert invalid.isError
                invalid = await client.call_tool('household_record', {'request_id':'mcp-invalid-date','changes':[
                    {'action':'add_item','name':'牛奶','quantity':1,'unit':'盒','location':'冷藏','due':'2026-02-30'}]})
                assert invalid.isError
                await client.call_tool('household_undo', {'request_id':'mcp-items-undo'})
                result = await client.call_tool('household_query', {'scope':'items'})
                assert json.loads(result.content[0].text)['item_count'] == 0
                saved = await client.call_tool('household_record', {'request_id':'test-mcp-draft-save', 'draft_text':'测试物品数量和位置待补充'})
                assert json.loads(saved.content[0].text)['status'] == 'draft'
                drafts = await client.call_tool('household_query', {'scope':'drafts', 'limit':3})
                row = json.loads(drafts.content[0].text)['records'][0]
                args = {'request_id':'test-mcp-draft-complete', 'draft_id':row['draft_id'],
                        'expected_draft_version':row['version'], 'changes':[
                            {'action':'add_item','name':'测试补全物品','quantity':1,'unit':'盒','location':'测试抽屉'}]}
                result = await client.call_tool('household_record', args)
                assert not result.isError and json.loads(result.content[0].text)['draft']['state'] == 'completed'
                result = await client.call_tool('household_record', args)
                assert json.loads(result.content[0].text)['replayed']
                await client.call_tool('household_undo', {'request_id':'test-mcp-draft-undo'})
                drafts = await client.call_tool('household_query', {'scope':'drafts'})
                row = json.loads(drafts.content[0].text)['records'][0]
                assert row['version'] == 3
                result = await client.call_tool('household_record', {'request_id':'test-mcp-draft-cancel',
                    'draft_id':row['draft_id'],'expected_draft_version':3,'cancel_draft':True})
                assert json.loads(result.content[0].text)['draft']['state'] == 'cancelled'
                invalid = await client.call_tool('household_query', {'scope':'drafts','name':'测试'})
                assert invalid.isError
                invalid = await client.call_tool('household_query', {'scope':'items','draft_state':'all'})
                assert invalid.isError
                invalid = await client.call_tool('household_record', {'request_id':'test-mcp-mixed-draft',
                    'draft_text':'测试混用', 'changes':args['changes']})
                assert invalid.isError
    asyncio.run(run())
