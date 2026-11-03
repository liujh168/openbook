# 象棋开局库转换与查询工具

项目提供三个数据路径：

- `convert_obk.py` + `bhobk.exe`：将原 `test.obk` 或 CCBridge3 `.CBL` 转为 jqxq 私有的 `book.bin`，按权重查询。
- `obk.py`：继续查询原始 SQLite OBK，显示评分、胜/和/负、有效标记和备注。
- `cbl.py`：独立解析 CCBridge3 CBL/CBR，提供棋盘、棋谱信息、注解及主变/变着树。

原 `test.obk` 和输入 CBL 均保持不变。C 版默认读取 `book.bin`，不再访问 SQLite。

## 快速开始

```bat
bhobk.exe                    :: 查询初始局面（显示帮助提示）
bhobk.exe -h                 :: 查看命令行帮助（也支持 --help）
bhobk.exe "<FEN>"            :: 查询任意局面（FEN 含空格要加引号）
bhobk.exe --key <vkey>       :: 按 jqxq key 查询，支持十进制和 0x 十六进制
bhobk.exe --demo             :: 查询初始目标 key 0x52DFA0347C3B4C0F
bhobk.exe --play 炮二平五 马8进7   :: 分叉跟踪（中文着法或 ICCS 均可）
bhobk.exe --play             :: 交互式分叉跟踪（b=回退，空行/q 退出）
bhobk.exe --book other.bin   :: 指定二进制开局库
bhobk.exe --check            :: 检查默认 book.bin
bhobk.exe --book other.bin --check  :: 检查指定二进制库
```

`--book` 和 `--check` 需放在其他查询参数之前。C 查询输出为中文着法、ICCS 和权重，按权重降序；合法时 `--check` 返回退出码 0，否则返回 1。

初始目标局面有 3 条候选：

```text
vkey: 5971667778199571471
炮二平五    h2-e2     1545
兵七进一    c3-c4      749
相三进五    g0-e2      705
```

原始 OBK 查询与分叉跟踪：

```bash
python obk.py                 # 查初始局面
python obk.py "<FEN>"         # 查任意 FEN，显示文本棋盘
python obk.py --key <vkey>    # 按原 OBK 十进制 vkey 查
python obk.py --demo          # 查高位 REAL 位模式演示 key
python obk.py --db other.obk --demo       # 指定原始 SQLite OBK
python obk.py --check                     # 检查默认 test.obk
python obk.py --db other.obk --check      # 检查指定 OBK
python obk.py --play 炮二平五 马8进7       # 批量分叉跟踪
python obk.py --play h2-e2 h9-g7          # 使用 ICCS 着法
python obk.py --play                      # 交互跟踪，b=回退，空行/q 退出
```

Python 版 `--db` 读取原始 `.obk`，与 C 版读取二进制库的 `--book` 不同。`--check` 只读执行 SQLite 快速检查并验证 `bhobk` 必需字段，合法时返回 0，否则返回 1。分叉按评分降序显示，逐步报告在谱、到边界、脱谱或已出谱状态，并保留胜/和/负、禁用标记和备注查询能力。

## 转换为 book.bin

```bat
python convert_obk.py
python convert_obk.py test.obk -o book.bin
python convert_obk.py other.obk -o book.bin --merge
python convert_obk.py "中炮对单提马新变.CBL" -o cbl_book.bin
python convert_obk.py --verify book.bin
```

可选 `--max-plies N` 限制遍历半回合数；OBK 从初始局面计算深度，CBL 则分别限制每局棋的深度，默认均不限。默认每次从空库开始并覆盖目标；指定 `--merge` 时，目标文件必须已存在且通过格式校验，转换器会先读入已有记录，再与新来源按 `(key, move)` 合并，重复项权重相加并饱和至 65535。

转换器只读打开 SQLite 或读取 CBL，并在同目录临时文件写入、校验后原子替换目标文件。

OBK 转换语义：

- 只接受 `vvalid=1` 的记录，禁用记录不写入，也不沿其继续遍历。
- `count = vwin + vdraw + vlost`；零权重记录可继续遍历，但自身不写入。
- 重复 `(key, move)` 合并，权重饱和至 65535，`learn=0`。
- 可达的非法着法会带源 rowid 报错并停止，不猜测或强行转换。
- 不可达记录不写入；没有局面键的 `vkey=NULL` 记录也归入不可达统计。
- `vscore`、分开的胜/和/负、`vmemo`、`vindex` 和禁用记录无法保留在目标格式中。

当前 `test.obk` 完整转换结果为 **377 条记录、285 个局面、6032 字节**。转换结束会报告源记录、输出记录/局面、可达禁用、零权重、不可达及权重饱和统计。

CBL 转换语义：

- 支持 CCBridge3 的 `CCBridgeLibrary` 棋库，解析棋盘、先行方、注解以及主变/变着树。说明书中的 2.09/2.1 版 `CCBridge` 是另一种旧格式，目前不在命令行支持范围内。
- CBL 不含着法权重；每个合法存储着法贡献权重 1，跨棋谱及分支重复时累加并饱和至 65535。
- 转换时检查完整行棋合法性。遇到非法着法时跳过该分支及其后继，继续处理其他分支，并报告跳过分支数和着法数。
- 棋盘、标题、棋手和注解用于解析，但目标格式仍只保留局面键、着法和权重。

所附 `中炮对单提马新变.CBL` 含 1 局大型开局树、32253 步着法；转换导入 32242 步，跳过 3 个非法分支共 11 步，生成 **31073 条记录、30553 个局面、497168 字节**。

## 数据格式

### jqxq book.bin

每条记录固定 16 字节，小端 `<QHHI`：

| 字段 | 类型 | 含义 |
|---|---|---|
| key | uint64 | jqxq Zobrist 局面键 |
| move | uint16 | `(from << 8) \| to`，16×16 mailbox 坐标 |
| count | uint16 | 胜、和、负总数，非零 |
| learn | uint32 | 保留，固定为 0 |

记录严格按 `(key, move)` 排序，C 查询器使用二分查找。目标哈希使用 `jqxq_zobrist.h` 的 3842 个常量，黑方走子时异或第 3840 项；初始 key 为 `0x52DFA0347C3B4C0F`。转换器解析同一头文件，避免 C/Python 常量不一致。

该格式仅沿用 Polyglot 的条目布局，不能读取标准国际象棋 Polyglot 库。

### 原始 test.obk

SQLite 表 `bhobk` 包含 `vkey`、`vmove`、`vscore`、`vwin`、`vdraw`、`vlost`、`vvalid`、`vmemo` 和 `vindex`。原 OBK key 使用 `zobrist_table.py` 的 `ZT[14][256]`，红方走子异或 `ZP`，初始 key 为 `7101337512282506414`。高位键在 SQLite 中按 REAL 的 8 字节位模式保存，`obk.py` 与转换器均兼容 INTEGER/REAL 两种形式。

## 编译

```bat
build.bat
```

使用便携版 TinyCC（`tcc/`，无需安装）将 `bhobk.c` 编译为单个 EXE。C 版只需 `jqxq_zobrist.h`，不再编译 SQLite。

## 回归测试

```bat
python -m unittest discover -s tests -v
```

测试仅使用 Python 标准库，会先执行实际转换和 `build.bat`。覆盖 OBK/CBL 转换语义、CBL 主变/变着与非法分支、mailbox 走法、INTEGER/REAL 高位键、合并饱和、损坏输入、C 查询与分叉，以及原 Python OBK 的已知结果、库校验、批量/交互分叉和错误处理。

## 文件清单

| 文件 | 说明 |
|---|---|
| `convert_obk.py` | 独立 OBK/CCBridge3 CBL → jqxq 二进制库转换器 |
| `cbl.py` | CCBridge3 CBL/CBR 棋盘、注解和变着树解析器 |
| `book.bin` | 已生成并校验的 jqxq 开局库 |
| `jqxq_zobrist.h` | C/Python 共用的目标 Zobrist 常量 |
| `bhobk.c` / `bhobk.exe` | 二进制库查询与分叉跟踪工具 |
| `obk.py` | 原始 SQLite OBK 查询、校验与分叉跟踪工具 |
| `test.obk` | 原始开局库，保持不变 |
| `zobrist.h` / `zobrist_table.py` | 原 OBK Zobrist 表 |
| `xqgen.py` | 转换器与 OBK 分叉共用的伪合法走法生成器 |
| `tests/` | 转换与命令行回归测试 |
| `tcc/` | 便携版 TinyCC 0.9.27 |
| `LICENSE` | jqxq 与 cchess 所采用的 GPL-3.0+ 许可文本 |

OBK 转换算法和目标随机表提取自 jqxq（GPL-3.0+），源文件为 `tests/make_book.py`、`tests/xiangqi_oracle.py` 和 `zobrist.cpp`。CBL 二进制布局参考 [walker8088/cchess](https://github.com/walker8088/cchess) 的 `src/cchess/read_cbr.py`（GPL-3.0+），已改为独立数据模型和有界读取；相关来源与许可说明保留在源码中。
