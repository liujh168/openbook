# OBK 象棋开局库查询工具

开局库 `test.obk` 本质是 SQLite 数据库，存 15.6 万条局面着法（评分 + 胜/和/负统计）。

## 快速开始

```bat
bhobk.exe                    :: 查询初始局面（显示帮助提示）
bhobk.exe -h                 :: 查看命令行帮助（也支持 --help）
bhobk.exe "<FEN>"            :: 查询任意局面（FEN 含空格要加引号）
bhobk.exe --key <vkey>       :: 直接按 vkey 查（无棋盘，显示原始走法码）
bhobk.exe --demo             :: 查询演示 key 15265892774299731920
bhobk.exe --play 炮二平五 马8进7   :: 分叉跟踪（中文着法或 ICCS 均可）
bhobk.exe --play             :: 交互式分叉跟踪（b=回退，空行/q 退出）
bhobk.exe --db other.obk     :: 指定开局库，可配合其他查询参数使用
bhobk.exe --check            :: 快速检查默认 test.obk 是否合法
bhobk.exe --db other.obk --check  :: 快速检查指定开局库
```

`--db` 和 `--check` 需放在其他查询参数之前。检查包括 SQLite `quick_check` 以及 `bhobk` 表和查询必需字段；合法时退出码为 0，否则为 1。

Python 等价工具（便于脚本集成）：

```bash
python obk.py                 # 查初始局面
python obk.py "<FEN>"         # 查任意 FEN
python obk.py --key <vkey>    # 按 vkey 查
```

查询输出：中文着法 + ICCS 坐标 + 评分 + 胜/和/负盘数 + 有效标记（1=推荐，0=被做库者禁用），按评分降序。

示例（初始局面）：

```
vkey: 7101337512282506414
炮二平五    h2-e2     949  292  957  296    1
相三进五    g0-e2     576  150  462   93    1
兵七进一    c3-c4     412  146  442  161    1
```

## 数据格式（test.obk）

SQLite 数据库，表 `bhobk`：

| 列 | 含义 |
|---|---|
| vkey | 局面 Zobrist 哈希（64 位，见下） |
| vmove | 走法编码：`(from << 8) \| to`，坐标为 16×16 mailbox（左上角 0x33） |
| vscore | 评分 |
| vwin / vdraw / vlost | 胜 / 和 / 负盘数 |
| vvalid | 1=允许，0=禁用 |
| vmemo | 备注（GBK 编码 BLOB） |
| vindex | 开局步数（大多为空） |

### vkey 计算约定（已与库内数据验证一致）

- 棋盘格号：16×16 mailbox，`sq = ((row+3) << 4) | (col+3)`，row 0 = 黑方底线
- 棋子编号：红 帅0 仕1 相2 马3 车4 炮5 兵6；黑 将7 士8 象9 马10 车11 炮12 卒13
- `key = XOR(ZT[棋子][格号])`，红方走子时再 `XOR 11587246140411948888`（ZP）
- 随机表 `ZT[14][256]` 在 `zobrist.h` / `zobrist_table.py`，提取自 `局面HASHKEY计算.txt`
- 验证锚点：初始局面 key = **7101337512282506414**
- **注意**：key ≥ 2⁶³ 时库里按「位模式重解释的 REAL」（double 的 8 字节 = key 的 8 字节）存储，查询需按此绑定参数；key < 2⁶³ 按 INTEGER 存储

## 编译

```bat
build.bat
```

使用便携版 TinyCC（`tcc/`，无需安装），将 `bhobk.c` 与 SQLite 3.54.1 源码（`sqlite-amalgamation-3540100/`）直接编译为单个 exe，约 1.4 MB，无外部依赖。

> 提示：编译后若立即运行报"拒绝访问"，是 Windows 安全软件在扫描新 exe，稍等一两秒即可。

## 回归测试

```bat
python -m unittest discover -s tests -v
```

测试使用 Python 标准库 `unittest`，会先执行 `build.bat`，再通过真实命令行验证当前程序。首轮固定初始局面 15 条结果、高位 vkey、C/Python 一致性、中文与 ICCS 分叉跟踪，以及 `--db` / `--check` 的正常和异常路径，不遍历全部开局库记录。

## 文件清单

| 文件 | 说明 |
|---|---|
| `bhobk.c` / `bhobk.exe` | C 版查询工具（含 FEN、中文着法翻译、分叉跟踪） |
| `obk.py` | Python 版查询工具 |
| `xqgen.py` | 走法生成器（验证/集成用） |
| `zobrist.h` / `zobrist_table.py` | Zobrist 哈希表（C / Python 版） |
| `test.obk` | 开局库|
| `shim.h` | TinyCC 兼容垫片（补充其头文件缺失的 Win32 声明） |
| `tcc/` | 便携版 TinyCC 0.9.27 |

## 更新记录（2026-11-1）
