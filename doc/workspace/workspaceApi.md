# workspace agent间通信
## api
```
http://192.168.34.65:58091/api/communicate
```

## describe
```
该接口用于工作空间内 Agent 之间的通信，尤其是 Master Agent 与 Worker Agent 之间的消息传递。通过这个接口，Master Agent 可以向 Worker Agent 发送指令或查询，Worker Agent 也可以向 Master Agent 汇报状态或请求帮助。
```

## method
```
POST
```

## parameters
| 参数 | 说明 | 类型 | 是否必填 | 默认值 |
|------|------|------|----------|--------|
| agent_port | agent 端口 | number | 是 | 无 |
| conversation_id | 会话 ID | string | 否 | 无 |
| messages | 消息列表，格式同 OpenAI Chat API | array | 是 | 无 |
| api_key | API 密钥 | string | 是 | 无 |
| stream | 是否启用流式输出 | boolean | 否 | true |

## response
| 参数 | 说明 | 类型 | 默认值 |
|------|------|------|----------|--------|
| code | 响应码 | number | 无 |
| status | 状态 | string | 无 |
| conversation_id | 会话 ID | string | 无 |
| output | Agent 回复的消息列表，格式同 OpenAI Chat API | array | 无 |

## example
```json
{
    "agent_port": 18000,
    "conversation_id": "conv456",
    "input": "Hello", 
    "store": true,
    "api_key": "218992cab0a24cc9a61eca241f06c59",
    "stream": true
}
```

## response
```json
{
    "code": 0,
    "status": "success",
    "conversation_id": "resp_7454ad69d0844351b5a5d3dfcad8",
    "output": [{
            "type": "function_call", 
            "name": "session_search", 
            "arguments": "{\"query\": \"SQL Server OceanBase\", \"limit\": 5}", 
            "call_id": "call_00_n6VzjaEbBQqSRMADczWe4828"
        }, {
            "type": "function_call_output", 
            "call_id": "call_00_n6VzjaEbBQqSRMADczWe4828", 
            "output": "{\"success\": true, \"mode\": \"discover\", \"query\": \"SQL Server OceanBase\", \"results\": [{\"session_id\": \"api-8bc6e109584bf091\", \"when\": \"June 01, 2026 at 03:37 AM\", \"source\": \"api_server\", \"model\": \"deepseek-v4-pro\", \"title\": null, \"matched_role\": \"assistant\", \"match_message_id\": 2, \"snippet\": \"Hello! I'm your >>>SQL<<< >>>Server<<< to >>>OceanBase<<< database conversion and operations expert. I can help with:\
            \
            - >>>SQL<<< >>>Server<<< to >>>OceanBase<<< MySQL >>>SQL<<< conversion (stored procedures, views, triggers, functions)\
            - Data type mapping between the two platforms\
            - Testing and validating converted...\", \"bookend_start\": [], \"messages\": [{\"id\": 1, \"role\": \"user\", \"content\": \"Hello!\", \"timestamp\": 1780285080.444095}, {\"id\": 2, \"role\": \"assistant\", \"content\": \"Hello! I'm your SQL Server to OceanBase database conversion and operations expert. I can help with:\
            \
            - SQL Server to OceanBase MySQL SQL conversion (stored procedures, views, triggers, functions)\
            - Data type mapping between the two platforms\
            - Testing and validating converted SQL objects\
            - Troubleshooting database migration issues\
            \
            What would you like to work on?\", \"timestamp\": 1780285080.445415, \"anchor\": true}], \"bookend_end\": [], \"messages_before\": 1, \"messages_after\": 0}], \"count\": 1, \"sessions_searched\": 1}"
        }, {
            "type": "message", 
            "role": "assistant", 
            "content": [{
                "type": "output_text", 
                "text": "There's only one prior session in the history, and it was very brief:
                    - June 01, 2026 at 03:37 AM \u2014 You said: \"Hello!\" and I responded with my capabilities.
                    That's it. There's nothing else on record from you in past conversations. In this current session, your only message so far has also been \"Hello\" \u2014 so that's the entirety of what you've said. 
                    Is there something specific you're looking for, or a task you'd like me to help with?"
            }]
        }]
}
```


# curl call api
curl http://host.containers.internal:58091/api/communicate \
  -H "Content-Type: application/json" \
  -d '{
    "agent_port": 18000,
    "conversation_id": "conv456",
    "input": "Hello", 
    "store": true,
    "api_key": "e45cb82f2b414dabbe132747af1395c4"
}'

# 用curl测试
curl http://192.168.34.65:18000/v1/responses \
  -H "Authorization: Bearer 218992cab0a24cc9a61eca241f06c596" \
  -H "Content-Type: application/json" \
  -d '{"model": "hermes-agent", "input": "Hello", "conversation": "my-project", "store": true}'
  
curl http://192.168.34.65:18001/v1/responses \
  -H "Authorization: Bearer 72cf98e050dd4ea19902c2d7247e0642" \
  -H "Content-Type: application/json" \
  -d '{"model": "hermes-agent", "input": "Hello", "conversation": "my-project", "store": true, "stream": true}'


{
    "id": "resp_7454ad69d0844351b5a5d3dfcad8", 
    "object": "response", 
    "status": "completed", 
    "created_at": 1780285410, 
    "model": "hermes-agent", 
    "output": [{
            "type": "function_call", 
            "name": "session_search", 
            "arguments": "{\"query\": \"SQL Server OceanBase\", \"limit\": 5}", 
            "call_id": "call_00_n6VzjaEbBQqSRMADczWe4828"
        }, {
            "type": "function_call_output", 
            "call_id": "call_00_n6VzjaEbBQqSRMADczWe4828", 
            "output": "{\"success\": true, \"mode\": \"discover\", \"query\": \"SQL Server OceanBase\", \"results\": [{\"session_id\": \"api-8bc6e109584bf091\", \"when\": \"June 01, 2026 at 03:37 AM\", \"source\": \"api_server\", \"model\": \"deepseek-v4-pro\", \"title\": null, \"matched_role\": \"assistant\", \"match_message_id\": 2, \"snippet\": \"Hello! I'm your >>>SQL<<< >>>Server<<< to >>>OceanBase<<< database conversion and operations expert. I can help with:\
            \
            - >>>SQL<<< >>>Server<<< to >>>OceanBase<<< MySQL >>>SQL<<< conversion (stored procedures, views, triggers, functions)\
            - Data type mapping between the two platforms\
            - Testing and validating converted...\", \"bookend_start\": [], \"messages\": [{\"id\": 1, \"role\": \"user\", \"content\": \"Hello!\", \"timestamp\": 1780285080.444095}, {\"id\": 2, \"role\": \"assistant\", \"content\": \"Hello! I'm your SQL Server to OceanBase database conversion and operations expert. I can help with:\
            \
            - SQL Server to OceanBase MySQL SQL conversion (stored procedures, views, triggers, functions)\
            - Data type mapping between the two platforms\
            - Testing and validating converted SQL objects\
            - Troubleshooting database migration issues\
            \
            What would you like to work on?\", \"timestamp\": 1780285080.445415, \"anchor\": true}], \"bookend_end\": [], \"messages_before\": 1, \"messages_after\": 0}], \"count\": 1, \"sessions_searched\": 1}"
        }, {
            "type": "message", 
            "role": "assistant", 
            "content": [{
                "type": "output_text", 
                "text": "There's only one prior session in the history, and it was very brief:
                    - June 01, 2026 at 03:37 AM \u2014 You said: \"Hello!\" and I responded with my capabilities.
                    That's it. There's nothing else on record from you in past conversations. In this current session, your only message so far has also been \"Hello\" \u2014 so that's the entirety of what you've said. 
                    Is there something specific you're looking for, or a task you'd like me to help with?"
            }]
        }], 
    "usage": {"input_tokens": 28130, "output_tokens": 319, "total_tokens": 28449}}