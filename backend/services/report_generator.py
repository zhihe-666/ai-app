"""
报告生成器 — AI 编程数据报告编排

串行调用四个数据查询模块，格式化为 Markdown 片段，
最终组装为完整周报 Markdown。
"""
import logging
import os

from services.ai_measure_client import AiMeasureClient
from services.skills_query_client import SkillsQueryClient

logger = logging.getLogger(__name__)

# 默认 TL 名单（域账号格式，共 25 人+1空缺（陳飞未找到））
DEFAULT_TL_NAMES = (
    "yecheng02,xuxing02,fangkuan,wuji03,wangrui1207,wangjialin01,jiangzaifan,mayan521,"
    "qianyu01,xuyang711,liran,guoxiaowei,zhenghui0412,lisizhong,wangyuqi,zhangkui,"
    "huochenlong,chenyu1,xiaojun,yulianjiang,fanxiaojun,sanbai,ailiou,fangwei05,liuliuqiu"
)
TL_NAMES_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tl_names.txt")


def get_tl_names() -> str:
    """获取当前 TL 名单，优先从持久化文件读取，回退到默认"""
    try:
        if os.path.exists(TL_NAMES_FILE):
            with open(TL_NAMES_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    return content
    except Exception:
        pass
    return DEFAULT_TL_NAMES


def save_tl_names(names: str):
    """持久化 TL 名单到文件"""
    os.makedirs(os.path.dirname(TL_NAMES_FILE), exist_ok=True)
    with open(TL_NAMES_FILE, "w", encoding="utf-8") as f:
        f.write(names.strip())

# 默认试点人员名单（域账号，由用户提供）
DEFAULT_PILOT_NAMES = (
    "zoulei,zonghengshi,zhuyue02,zhuxingming,zhujianhua,zhuhuchao,zhouzijie,zhoudianrui,"
    "zhengxin04,zhengdu,zhangxiaojun,zhangxiaofei922,zhangshuai417,zhanghu1002,zhangchun0517,"
    "zhangbo12,zann,yuxiang06,yunxin,yumei,yulianjiang,yuhui03,yuhong02,yuanxiao01,youchai,"
    "yili,yijing01,yewei02,yeqiushi,yelifeng,yecheng02,yanshuiya,yangzidian,yangyu513,"
    "yangxiaochu,yanglei731,yangjin417,yanfeiran,yanchenxi,xuyingbing,xuxing02,xuwenqiang,"
    "xupengfei01,xuanmo01,xuanlin,xuanfeng,xingyun04,xinfeng,xiezhaodong,xiexin,xieweida,"
    "xiduo03,xibei01,xiaojun,xiahou,wuwenbin01,wuji03,wuhao,wucunhua,wuchengze,wubenhong,"
    "wenzheng01,weijihui,weijiang,weichao,wangzeqin,wangyuqing332,wangyukun01,wangyaoyao01,"
    "wangxu723,wangxinxin05,wangxinbo01,wangshicheng,wangliangliang01,wangle07,wangkang01,"
    "wangguotao,wangguojun,wangdasong,wangchaoyang,wangbowei,wanchen,tianrui01,tianheng,"
    "tianbei,tengling,tanyongqiang,tangseng,sujin,songziheng,songyuwen,simacuo,sicheng01,"
    "shitao,shishu,shengbai,shaocuiming,sanbai,ruoxu,ruitong01,renzhangqing,qiwan,qishuo02,"
    "qingyangzi,qingce,qifei03,qiaoyang,qianyu05,qiancheng1033,pengyuhang,penghuafeng,"
    "niangao01,muyan02,moyuan,mazhenxin,mayin01,mayan521,maoqiang01,maliou,lvjinqiu01,"
    "lvhuidong,lvhongpeng,lvhonghui,luoxiaowei,longkai,lixueyuan,lixinlei,lixingdong,"
    "liwenbiao,liuzequn,liuyaoyao01,liutao1033,lisizhong,liruigang,liran,linxingwei,"
    "lintian,linsong,lingqi,linchuan,lilongwei,likuan,likai08,lijianxin,lichao1213,"
    "libin04,lianxin,liangfengnian,lejianjun,leimeng02,leichao01,langzeyu,kongyangxin,"
    "kapai,jinchen05,jinbi01,jianxin02,jiangpeicheng,jiangnan02,jiachenghao,i_zhangzihao01,"
    "huyu1028,huochenlong,hufei02,huangli,huafei01,houchao,heze,heyi03,hejun309,haoyiqi,"
    "haoyan,hanlu03,guoxiaowei,guoqiwen,guli,guangzhi01,goushuai,futu,fengjiaxiao,"
    "fenghaidong,fanxiaojun,fangwei05,fangkuan,fangcheng01,dushaoyun,dongxuehui03,dengyao,"
    "daitianlun01,daguaishou,chuishi,chuanyun01,chenyu1,chenyang09,chenyang0324,chenxin08,"
    "chenqingguo,chenpengpeng,chenchangqing,changtao01,caozibiao,boyang03,baiyun03,"
    "baiyuehui,baihao01,anmingguo,anbingqiang,ailiou,guansha,lisunan,fuxiaohan01,"
    "xuyang711,xinghe01,yaoxing,xiejun03,huangruixin,jimingjie,wangrui1207,lijiajun01,"
    "zhenghui0412"
)

# 试点名单持久化文件路径
import os
PILOT_NAMES_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pilot_names.txt")


def get_pilot_names():
    """获取当前试点人员名单，优先从持久化文件读取，回退到默认"""
    try:
        if os.path.exists(PILOT_NAMES_FILE):
            with open(PILOT_NAMES_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    return content
    except Exception:
        pass
    return DEFAULT_PILOT_NAMES


def save_pilot_names(names: str):
    """持久化试点人员名单到文件"""
    os.makedirs(os.path.dirname(PILOT_NAMES_FILE), exist_ok=True)
    with open(PILOT_NAMES_FILE, "w", encoding="utf-8") as f:
        f.write(names.strip())

# 默认试点人员名单（域账号，由用户提供）
DEFAULT_PILOT_NAMES = (
    "zoulei,zonghengshi,zhuyue02,zhuxingming,zhujianhua,zhuhuchao,zhouzijie,zhoudianrui,"
    "zhengxin04,zhengdu,zhangxiaojun,zhangxiaofei922,zhangshuai417,zhanghu1002,zhangchun0517,"
    "zhangbo12,zann,yuxiang06,yunxin,yumei,yulianjiang,yuhui03,yuhong02,yuanxiao01,youchai,"
    "yili,yijing01,yewei02,yeqiushi,yelifeng,yecheng02,yanshuiya,yangzidian,yangyu513,"
    "yangxiaochu,yanglei731,yangjin417,yanfeiran,yanchenxi,xuyingbing,xuxing02,xuwenqiang,"
    "xupengfei01,xuanmo01,xuanlin,xuanfeng,xingyun04,xinfeng,xiezhaodong,xiexin,xieweida,"
    "xiduo03,xibei01,xiaojun,xiahou,wuwenbin01,wuji03,wuhao,wucunhua,wuchengze,wubenhong,"
    "wenzheng01,weijihui,weijiang,weichao,wangzeqin,wangyuqing332,wangyukun01,wangyaoyao01,"
    "wangxu723,wangxinxin05,wangxinbo01,wangshicheng,wangliangliang01,wangle07,wangkang01,"
    "wangguotao,wangguojun,wangdasong,wangchaoyang,wangbowei,wanchen,tianrui01,tianheng,"
    "tianbei,tengling,tanyongqiang,tangseng,sujin,songziheng,songyuwen,simacuo,sicheng01,"
    "shitao,shishu,shengbai,shaocuiming,sanbai,ruoxu,ruitong01,renzhangqing,qiwan,qishuo02,"
    "qingyangzi,qingce,qifei03,qiaoyang,qianyu05,qiancheng1033,pengyuhang,penghuafeng,"
    "niangao01,muyan02,moyuan,mazhenxin,mayin01,mayan521,maoqiang01,maliou,lvjinqiu01,"
    "lvhuidong,lvhongpeng,lvhonghui,luoxiaowei,longkai,lixueyuan,lixinlei,lixingdong,"
    "liwenbiao,liuzequn,liuyaoyao01,liutao1033,lisizhong,liruigang,liran,linxingwei,"
    "lintian,linsong,lingqi,linchuan,lilongwei,likuan,likai08,lijianxin,lichao1213,"
    "libin04,lianxin,liangfengnian,lejianjun,leimeng02,leichao01,langzeyu,kongyangxin,"
    "kapai,jinchen05,jinbi01,jianxin02,jiangpeicheng,jiangnan02,jiachenghao,i_zhangzihao01,"
    "huyu1028,huochenlong,hufei02,huangli,huafei01,houchao,heze,heyi03,hejun309,haoyiqi,"
    "haoyan,hanlu03,guoxiaowei,guoqiwen,guli,guangzhi01,goushuai,futu,fengjiaxiao,"
    "fenghaidong,fanxiaojun,fangwei05,fangkuan,fangcheng01,dushaoyun,dongxuehui03,dengyao,"
    "daitianlun01,daguaishou,chuishi,chuanyun01,chenyu1,chenyang09,chenyang0324,chenxin08,"
    "chenqingguo,chenpengpeng,chenchangqing,changtao01,caozibiao,boyang03,baiyun03,"
    "baiyuehui,baihao01,anmingguo,anbingqiang,ailiou,guansha,lisunan,fuxiaohan01,"
    "xuyang711,xinghe01,yaoxing,xiejun03,huangruixin,jimingjie,wangrui1207,lijiajun01,"
    "zhenghui0412"
)

# 每个 section 的表头定义
SECTION_CONFIGS = [
    ("active_rate", "试点人员活跃率",
     "| 姓名 | 活跃率 | 人均总Tokens(M) | AI生成代码占比 | AI Commit代码占比 |",
     "|------|--------|----------------|---------------|------------------|"),
    ("inactive", "不活跃人员名单",
     "| 姓名 | 域账号 | 部门 | 活跃率 | AI生成代码占比 | AI Commit代码占比 |",
     "|------|--------|------|--------|---------------|------------------|"),
    ("skills", "Skills 技能列表",
     "| 技能名称 | 贡献人 | 技能描述 | 调用次数 | 提效分钟 | 更新时间 |",
     "|----------|--------|---------|---------|---------|---------|"),
    ("tl_usage", "算法TL AI编程使用情况",
     "| 姓名 | 活跃率 | 人均总Tokens(M) | AI生成代码占比 | AI Commit代码占比 |",
     "|------|--------|----------------|---------------|------------------|"),
]


class ReportGenerator:
    """数据报告编排器"""

    def __init__(self, token: str = None):
        self.ai_client = AiMeasureClient(token=token)
        self.skills_client = SkillsQueryClient(token=token)
        # 缓存：pilot 全量数据（懒加载）
        self._pilot_cache_key = None
        self._pilot_cache_data = None

    def _ensure_pilot_data(self, pilot_names: str, start_date: str, end_date: str) -> dict:
        """确保有缓存数据 —— 懒加载，有缓存返回缓存，无缓存调 API
        
        第一次调 active_rate 时触发实际 API 请求，之后 inactive 复用缓存。
        """
        cache_key = f"{pilot_names}|{start_date}|{end_date}"
        if self._pilot_cache_key == cache_key and self._pilot_cache_data is not None:
            return self._pilot_cache_data
        # 缓存未命中，调 API
        data = self.ai_client.query_all_pilot_data(
            department="技术部",
            start_date=start_date,
            end_date=end_date,
            names=pilot_names,
        )
        self._pilot_cache_key = cache_key
        self._pilot_cache_data = data
        return data

    def query_section(self, section_id: str, pilot_names: str,
                      start_date: str, end_date: str) -> dict:
        """查询单个 section 的数据

        注意：active_rate 和 inactive 共用一次API查询（拆表），
        active_rate 返回全部，inactive 从中筛选不活跃。

        Returns:
            {"rows": [dict, ...], "error": str|None}
        """
        try:
            if section_id == "active_rate":
                return self._ensure_pilot_data(pilot_names, start_date, end_date)
            elif section_id == "inactive":
                all_data = self._ensure_pilot_data(pilot_names, start_date, end_date)
                inactive = []
                for row in all_data.get("rows", []):
                    if row.get("activity_rate_null", True):
                        continue
                    is_active = (row["activity_rate"] >= 40) or (row["consumption"] >= 3000)
                    if not is_active:
                        inactive.append(row)
                return {"rows": inactive}
            elif section_id == "skills":
                return self.skills_client.query_skills(
                    department="技术部",
                    names=pilot_names,
                    start_date=start_date,
                    end_date=end_date,
                )
            elif section_id == "tl_usage":
                tl_names = get_tl_names()
                result = self.ai_client.query_active_rate(
                    department="技术部",
                    start_date=start_date,
                    end_date=end_date,
                    names=tl_names,
                )
                return result
            else:
                return {"rows": [], "error": f"未知 section_id: {section_id}"}
        except Exception as e:
            logger.error(f"查询 section {section_id} 失败: {e}")
            return {"rows": [], "error": str(e)}

    def format_section_markdown(self, section_id: str, title: str, data: dict) -> str:
        """将查询数据格式化为 Markdown 表格块"""
        rows = data.get("rows", [])
        if not rows:
            return f"## {title}\n\n（无数据）\n"

        # 获取对应表头
        header_line, separator_line = "", ""
        for sid, stitle, hdr, sep in SECTION_CONFIGS:
            if sid == section_id:
                header_line, separator_line = hdr, sep
                break

        lines = [f"## {title}\n", header_line, separator_line]

        for row in rows:
            if section_id in ("active_rate", "tl_usage"):
                lines.append(
                    f"| {row['name']} | {row['activity_rate']:.2f}% "
                    f"| {row['tokens_m']}M | {row['code_ratio']:.2f}% "
                    f"| {row['commit_ratio']:.2f}% |"
                )
            elif section_id == "inactive":
                lines.append(
                    f"| {row['name']} | {row.get('username', '-')} "
                    f"| {row['department']} | {row['activity_rate']:.2f}% "
                    f"| {row['code_ratio']:.2f}% | {row['commit_ratio']:.2f}% |"
                )
            elif section_id == "skills":
                lines.append(
                    f"| {row.get('skill_link', row['name'])} | {row['author']} "
                    f"| {row.get('description', '-')} "
                    f"| {row.get('call_count', '-')} "
                    f"| {row.get('efficiency_minutes', '-')} "
                    f"| {row.get('updated_at', '-')} |"
                )

        return "\n".join(lines)

    def generate_full_report(self, pilot_names: str, start_date: str, end_date: str,
                             sections: list[str]) -> str:
        """生成完整报告 Markdown（非流式，直接汇总）"""
        report_parts = [
            f"# 算法平台 AI 编程周报（{start_date} ~ {end_date}）\n"
        ]

        for section_id, section_title, _, _ in SECTION_CONFIGS:
            if section_id not in sections:
                continue
            data = self.query_section(section_id, pilot_names, start_date, end_date)
            section_md = self.format_section_markdown(section_id, section_title, data)
            report_parts.append(section_md)

        return "\n\n".join(report_parts)