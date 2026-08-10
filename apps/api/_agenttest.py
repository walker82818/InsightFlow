"""临时诊断：用伪 LLM 客户端跑通 ReAct 循环（无需真实 Key）。

验证：工具调用序列化、tool 消息回传、结果汇总、agent_end 事件。
"""
import asyncio
from collections.abc import AsyncIterator

from app.agent import DatasetRef, run_analysis
from app.agent.single_agent import AnalysisResult
from app.core.llm.base import LLMMessage, LLMResponse, ToolCall


class FakeLLM:
    def __init__(self):
        self.calls = 0

    async def chat(self, messages, *, tools=None, tool_choice="auto", temperature=0.0, max_tokens=None):
        self.calls += 1
        if self.calls == 1:
            # 第一轮：返回一条 SQL 工具调用
            return LLMResponse(
                content=None,
                tool_calls=[
                    ToolCall(
                        id="call_1",
                        name="sql_execute",
                        arguments={
                            "sql": "SELECT region, SUM(revenue) AS rev "
                                   "FROM {tbl} GROUP BY region ORDER BY rev DESC"
                        },
                    )
                ],
                model="fake",
            )
        # 第二轮：基于工具结果给出最终答案
        return LLMResponse(
            content="各地区总收入：East 最高，West 最低（详见 SQL 结果）。",
            tool_calls=[],
            model="fake",
        )

    async def is_configured(self):
        return True


async def main():
    ref = DatasetRef(
        id="646e3eae-eb76-4148-8ef4-6d046ad4efc7",
        name="Sample Sales",
        storage_path="2026/08/ee27f6a1-1276-4864-9490-48f46e72ffb6_d433b750-b866-4364-b052-c473e61f2df6_sample_sales.csv",
        file_type="csv",
        table_name="ds_646e3eae_eb76_4148_8ef4_6d046ad4efc7",
        schema_text="- region (category)\n- revenue (float)",
    )
    # 替换 client 工厂
    import app.agent.single_agent as sa
    original = sa.get_llm_client
    sa.get_llm_client = lambda size: FakeLLM()

    events: list[dict] = []
    async for ev in run_analysis(ref, "每个地区的总收入是多少？"):
        events.append(ev)
        print("EVENT:", ev["type"], "->", str(ev)[:120])

    sa.get_llm_client = original

    end = [e for e in events if e["type"] == "agent_end"]
    assert end, "no agent_end event"
    res = end[0]["result"]
    assert res["tool_calls"] == 1, res
    assert res["sql_results"], "no sql results"
    assert res["answer"], "no answer"
    print("\nOK: ReAct loop produced answer + 1 sql result.")


asyncio.run(main())
