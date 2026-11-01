/*
 * bhobk.c — OBK 象棋开局库查询工具
 *
 * 用法:
 *   bhobk.exe                       查询初始局面
 *   bhobk.exe "<FEN>"               查询指定局面(FEN 含空格需加引号)
 *   bhobk.exe --key <vkey>          直接按 vkey 查询(无棋盘,只显示原始走法码)
 *   bhobk.exe --demo                查询演示 key 15265892774299731920
 *   bhobk.exe --play 着法1 着法2 .. 分叉跟踪(中文着法或 ICCS, 如 炮二平五 马8进7)
 *   bhobk.exe --play                交互式分叉跟踪(逐行输入着法, b=回退一步, 空行/q 退出)
 *   bhobk.exe --db <文件>           指定开局库(默认 test.obk)
 *   bhobk.exe --check               快速检查开局库是否合法
 *   bhobk.exe -h, --help            显示命令行帮助
 *
 * vkey 计算: Zobrist 哈希, 14 棋子 x 256 格随机表异或, 红走再异或 ZP。
 * 棋子编号: 红 帅0 仕1 相2 马3 车4 炮5 兵6; 黑 将7 士8 象9 马10 车11 炮12 卒13
 * 走法编码: move = (from << 8) | to, 坐标为 16x16 mailbox(左上角 0x33)
 */
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include "sqlite3.h"
#include "zobrist.h"

#ifdef _WIN32
#include <windows.h>
#endif

#define START_FEN "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"

sqlite3 *db;
static const char *book_path = "test.obk";

typedef struct book_entry_t {
    unsigned __int16 move ;
    __int32 score ;
    __int32 win_count ;
    __int32 draw_count ;
    __int32 lost_count ;
    unsigned __int16 valid ;
    char comments[64];
} book_entry_t ;

/* ---------- Zobrist 键计算 ---------- */

/* FEN 字母 -> 棋子编号, 返回 -1 表示非棋子 */
static int chess_id(char ch)
{
    switch(ch){
    case 'K': return 0;  case 'A': return 1;  case 'B': return 2;
    case 'N': return 3;  case 'R': return 4;  case 'C': return 5;
    case 'P': return 6;
    case 'k': return 7;  case 'a': return 8;  case 'b': return 9;
    case 'n': return 10; case 'r': return 11; case 'c': return 12;
    case 'p': return 13;
    }
    return -1;
}

/* 解析 FEN 到 board[10][9](0=空格), 返回是否红方走子; 失败返回 -1 */
static int fen_to_board(const char *fen, char board[10][9])
{
    int r, c;
    memset(board, 0, 100);
    for(r = 0; r < 10; r++)
    {
        c = 0;
        while(*fen && *fen != '/' && *fen != ' ')
        {
            if(*fen >= '1' && *fen <= '9')
                c += *fen - '0';
            else
            {
                if(c > 8 || chess_id(*fen) < 0) return -1;
                board[r][c++] = *fen;
            }
            fen++;
        }
        if(c != 9) return -1;
        if(*fen == '/') fen++;
        else if(r < 9) return -1;
    }
    /* 走子方: 缺省或 'w' 为红 */
    while(*fen == ' ') fen++;
    return (*fen == 'b') ? 0 : 1;
}

static unsigned __int64 board_to_key(char board[10][9], int red_to_move)
{
    unsigned __int64 key = 0;
    int r, c, id, sq;
    for(r = 0; r < 10; r++)
        for(c = 0; c < 9; c++)
            if(board[r][c])
            {
                id = chess_id(board[r][c]);
                sq = ((r + 3) << 4) | (c + 3);
                key ^= ZT[id][sq];
            }
    if(red_to_move) key ^= ZP;
    return key;
}

/* ---------- 开局库查询 ---------- */

int GetBookEntry(book_entry_t *entry, unsigned __int64 key)
{
    sqlite3_stmt *stmt = NULL ;
    int n = 0 ;
    sqlite3_prepare_v2(db, "select vmove,vscore,vwin,vdraw,vlost,vvalid,vmemo from bhobk where vkey=?;", -1, &stmt, NULL);
    if(!stmt) return 0 ;
    if(key < 0x8000000000000000ULL)
    {
        /* key 在 int64 范围内, 库中按 INTEGER 存储 */
        sqlite3_bind_int64(stmt, 1, (sqlite3_int64)key);
    }
    else
    {
        /* key 超过 int64 上限, 库中按位模式重解释的 REAL 存储 */
        double d ;
        memcpy(&d, &key, 8);
        sqlite3_bind_double(stmt, 1, d);
    }
    while(SQLITE_ROW == sqlite3_step(stmt) && n < 128)
    {
        const char *cm ;
        int len ;
        entry[n].move = (unsigned __int16)sqlite3_column_int(stmt, 0);
        entry[n].score = sqlite3_column_int(stmt, 1);
        entry[n].win_count = sqlite3_column_int(stmt, 2);
        entry[n].draw_count = sqlite3_column_int(stmt, 3);
        entry[n].lost_count = sqlite3_column_int(stmt, 4);
        entry[n].valid = (unsigned __int16)sqlite3_column_int(stmt, 5);
        cm = (const char*)sqlite3_column_text(stmt, 6);
        len = sqlite3_column_bytes(stmt, 6);
        if(cm && len > 0)
        {
            if(len > 63) len = 63;
            memcpy(entry[n].comments, cm, len);
            entry[n].comments[len] = 0;
        }
        n++;
    }
    sqlite3_finalize(stmt);
    return n ;
}

/* ---------- 中文着法翻译 ---------- */

/* 棋子名(UTF-8): 索引 = 棋子编号 */
static const char *NAMES[14] = {
    "帅","仕","相","马","车","炮","兵",
    "将","士","象","马","车","炮","卒"
};
static const char *CN_NUM[9] = {"一","二","三","四","五","六","七","八","九"};
static const char *FRONT5[5] = {"前","二","三","四","五"};

/* 纵线文字: 红方从右往左数(中文数字), 黑方从左往右数(阿拉伯数字) */
static void fword(int is_red, int col, char *out)
{
    int n = is_red ? (9 - col) : (col + 1);
    if(is_red) strcpy(out, CN_NUM[n - 1]);
    else sprintf(out, "%d", n);
}

/* move -> 中文着法, 如 炮二平五; board 为当前局面, 调用方保证走子方正确 */
static void move_cn(char board[10][9], unsigned __int16 mv, char *out)
{
    int fr = ((mv >> 12) & 0xF) - 3, fc = ((mv >> 8) & 0xF) - 3;
    int tr = ((mv >> 4) & 0xF) - 3, tc = (mv & 0xF) - 3;
    char ch, name_buf[8], fw[8];
    int is_red, id, r, cnt = 0, idx = 0, forward, steps;
    int rows[5];

    if(fr < 0 || fr > 9 || fc < 0 || fc > 8 || tr < 0 || tr > 9 || tc < 0 || tc > 8
       || !board[fr][fc])
    {
        sprintf(out, "<非法走法 %u>", mv);
        return;
    }
    ch = board[fr][fc];
    id = chess_id(ch);
    is_red = (id < 7);
    strcpy(name_buf, NAMES[id]);

    /* 同纵线同名棋子 -> 前/后/中 区分(按进的方向, 最前者为"前") */
    for(r = 0; r < 10; r++)
        if(board[r][fc] == ch && cnt < 5)
        {
            if(r == fr) idx = cnt;
            rows[cnt++] = r;
        }
    if(cnt >= 2)
    {
        /* rows 按 row 升序; 红方 row 小为前, 黑方 row 大为前 */
        int fi = is_red ? idx : (cnt - 1 - idx);
        if(cnt == 2)      sprintf(out, "%s%s", fi == 0 ? "前" : "后", name_buf);
        else if(cnt == 3) sprintf(out, "%s%s", fi == 0 ? "前" : fi == 1 ? "中" : "后", name_buf);
        else              sprintf(out, "%s%s", FRONT5[fi], name_buf);
    }
    else
    {
        fword(is_red, fc, fw);
        sprintf(out, "%s%s", name_buf, fw);
    }

    if(tr == fr)  /* 平 */
    {
        fword(is_red, tc, fw);
        strcat(out, "平");
        strcat(out, fw);
        return;
    }
    forward = is_red ? (tr < fr) : (tr > fr);
    strcat(out, forward ? "进" : "退");
    if(id % 7 == 1 || id % 7 == 2 || id % 7 == 3)  /* 仕相马/士象马: 记目标纵线 */
    {
        fword(is_red, tc, fw);
        strcat(out, fw);
    }
    else  /* 车炮帅将兵卒: 记步数 */
    {
        steps = tr > fr ? tr - fr : fr - tr;
        if(is_red) strcat(out, CN_NUM[steps - 1]);
        else { char nb[4]; sprintf(nb, "%d", steps); strcat(out, nb); }
    }
}

/* move -> ICCS 坐标, 如 h2-e2 (rank 0 = 红方底线) */
static void move_iccs(unsigned __int16 mv, char *out)
{
    int fr = ((mv >> 12) & 0xF) - 3, fc = ((mv >> 8) & 0xF) - 3;
    int tr = ((mv >> 4) & 0xF) - 3, tc = (mv & 0xF) - 3;
    sprintf(out, "%c%d-%c%d", 'a' + fc, 9 - fr, 'a' + tc, 9 - tr);
}

/* vmemo 是 GBK 编码, 转 UTF-8 输出 */
static void memo_utf8(const char *in, char *out, int outsz)
{
#ifdef _WIN32
    wchar_t w[128];
    if(MultiByteToWideChar(936, 0, in, -1, w, 128) > 0)
    {
        WideCharToMultiByte(65001, 0, w, -1, out, outsz, NULL, NULL);
        return;
    }
#endif
    strncpy(out, in, outsz - 1);
    out[outsz - 1] = 0;
}

/* 按评分降序 */
static int cmp_entry(const void *a, const void *b)
{
    return ((const book_entry_t*)b)->score - ((const book_entry_t*)a)->score;
}

/* 显示宽度: ASCII 计 1, 中文字符计 2 */
static int disp_width(const char *s)
{
    int w = 0;
    while(*s)
    {
        if((*s & 0xC0) != 0x80) w += (*s & 0x80) ? 2 : 1;
        s++;
    }
    return w;
}
static void print_pad(const char *s, int w)
{
    int d = disp_width(s);
    fputs(s, stdout);
    while(d++ < w) putchar(' ');
}

/* ---------- 编码工具 ---------- */

/* 是否合法 UTF-8(粗略) */
static int valid_utf8(const char *s)
{
    while(*s)
    {
        if((*s & 0x80) == 0) { s++; continue; }
        if((*s & 0xE0) == 0xC0 && (s[1] & 0xC0) == 0x80) { s += 2; continue; }
        if((*s & 0xF0) == 0xE0 && (s[1] & 0xC0) == 0x80 && (s[2] & 0xC0) == 0x80) { s += 3; continue; }
        return 0;
    }
    return 1;
}

/* 非 UTF-8 输入按 GBK(CP_ACP) 转 UTF-8; 已是 UTF-8 则原样拷贝 */
static void to_utf8(const char *in, char *out, int outsz)
{
#ifdef _WIN32
    wchar_t w[512];
    if(!valid_utf8(in) && MultiByteToWideChar(936, 0, in, -1, w, 512) > 0)
    {
        WideCharToMultiByte(65001, 0, w, -1, out, outsz, NULL, NULL);
        return;
    }
#endif
    strncpy(out, in, outsz - 1);
    out[outsz - 1] = 0;
}

/* ---------- 走法生成(伪合法, 开局跟踪够用) ---------- */

typedef struct { int fr, fc, tr, tc; } move_t;

#define ADD_MV(r2, c2) do { \
    char p_ = board[r2][c2]; \
    if(!p_ || (chess_id(p_) < 7) != red) { mvs[n].fr = r; mvs[n].fc = c; \
        mvs[n].tr = r2; mvs[n].tc = c2; n++; } } while(0)
#define ON_BOARD(r2, c2) ((r2) >= 0 && (r2) <= 9 && (c2) >= 0 && (c2) <= 8)

static int gen_moves(char board[10][9], int red, move_t *mvs)
{
    int n = 0, r, c, k;
    for(r = 0; r < 10; r++) for(c = 0; c < 9; c++)
    {
        char ch = board[r][c];
        int id, t;
        if(!ch) continue;
        id = chess_id(ch);
        if((id < 7) != red) continue;
        t = id % 7;   /* 0帅将 1仕士 2相象 3马 4车 5炮 6兵卒 */
        if(t == 6)  /* 兵卒 */
        {
            int fwd = red ? -1 : 1;
            int crossed = red ? (r <= 4) : (r >= 5);
            if(ON_BOARD(r + fwd, c)) ADD_MV(r + fwd, c);
            if(crossed)
            {
                if(c + 1 <= 8) ADD_MV(r, c + 1);
                if(c - 1 >= 0) ADD_MV(r, c - 1);
            }
        }
        else if(t == 0)  /* 帅将: 宫内直走一格 */
        {
            static const int D4[4][2] = {{1,0},{-1,0},{0,1},{0,-1}};
            int rmin = red ? 7 : 0, rmax = red ? 9 : 2;
            for(k = 0; k < 4; k++)
            {
                int r2 = r + D4[k][0], c2 = c + D4[k][1];
                if(r2 >= rmin && r2 <= rmax && c2 >= 3 && c2 <= 5) ADD_MV(r2, c2);
            }
        }
        else if(t == 1)  /* 仕士: 宫内斜走一格 */
        {
            static const int DD[4][2] = {{1,1},{1,-1},{-1,1},{-1,-1}};
            int rmin = red ? 7 : 0, rmax = red ? 9 : 2;
            for(k = 0; k < 4; k++)
            {
                int r2 = r + DD[k][0], c2 = c + DD[k][1];
                if(r2 >= rmin && r2 <= rmax && c2 >= 3 && c2 <= 5) ADD_MV(r2, c2);
            }
        }
        else if(t == 2)  /* 相象: 田字, 不过河, 塞象眼 */
        {
            static const int DD[4][2] = {{2,2},{2,-2},{-2,2},{-2,-2}};
            for(k = 0; k < 4; k++)
            {
                int r2 = r + DD[k][0], c2 = c + DD[k][1];
                if(ON_BOARD(r2, c2) && (red ? r2 >= 5 : r2 <= 4) && !board[r + DD[k][0]/2][c + DD[k][1]/2])
                    ADD_MV(r2, c2);
            }
        }
        else if(t == 3)  /* 马: 日字, 蹩马腿 */
        {
            static const int ND[8][4] = {{2,1,1,0},{2,-1,1,0},{-2,1,-1,0},{-2,-1,-1,0},
                                         {1,2,0,1},{1,-2,0,-1},{-1,2,0,1},{-1,-2,0,-1}};
            for(k = 0; k < 8; k++)
            {
                int r2 = r + ND[k][0], c2 = c + ND[k][1];
                if(ON_BOARD(r2, c2) && !board[r + ND[k][2]][c + ND[k][3]]) ADD_MV(r2, c2);
            }
        }
        else  /* 车/炮: 直线, 炮隔子吃 */
        {
            static const int D4[4][2] = {{1,0},{-1,0},{0,1},{0,-1}};
            for(k = 0; k < 4; k++)
            {
                int r2 = r + D4[k][0], c2 = c + D4[k][1], jumped = 0;
                while(ON_BOARD(r2, c2))
                {
                    char p = board[r2][c2];
                    if(t == 4)  /* 车 */
                    {
                        if(!p) ADD_MV(r2, c2);
                        else { if((chess_id(p) < 7) != red) ADD_MV(r2, c2); break; }
                    }
                    else  /* 炮 */
                    {
                        if(!jumped)
                        {
                            if(!p) ADD_MV(r2, c2);
                            else jumped = 1;
                        }
                        else if(p)
                        {
                            if((chess_id(p) < 7) != red) ADD_MV(r2, c2);
                            break;
                        }
                    }
                    r2 += D4[k][0]; c2 += D4[k][1];
                }
            }
        }
    }
    return n;
}

static unsigned __int16 pack_move(move_t m)
{
    return (unsigned __int16)((((m.fr + 3) << 4) | (m.fc + 3)) << 8 | (((m.tr + 3) << 4) | (m.tc + 3)));
}

static void apply_move(char board[10][9], unsigned __int16 mv)
{
    int fr = ((mv >> 12) & 0xF) - 3, fc = ((mv >> 8) & 0xF) - 3;
    int tr = ((mv >> 4) & 0xF) - 3, tc = (mv & 0xF) - 3;
    board[tr][tc] = board[fr][fc];
    board[fr][fc] = 0;
}

static int iccs_eq(const char *a, const char *b)  /* 忽略大小写比较 */
{
    while(*a && *b)
    {
        char x = *a, y = *b;
        if(x >= 'A' && x <= 'Z') x += 32;
        if(y >= 'A' && y <= 'Z') y += 32;
        if(x != y) return 0;
        a++; b++;
    }
    return *a == *b;
}

/* 把用户输入(中文着法或 ICCS)解析为走法码; 成功返回 1 */
static int parse_move(char board[10][9], int red, const char *s, unsigned __int16 *out)
{
    move_t mvs[256];
    int i, n = gen_moves(board, red, mvs);
    for(i = 0; i < n; i++)
    {
        unsigned __int16 mv = pack_move(mvs[i]);
        char cn[32], ic[16];
        move_cn(board, mv, cn);
        if(!strcmp(cn, s)) { *out = mv; return 1; }
        move_iccs(mv, ic);
        if(iccs_eq(ic, s)) { *out = mv; return 1; }
    }
    return 0;
}

/* ---------- 分叉跟踪 ---------- */

/* 打印文本棋盘: 上黑(繁体)下红(简体), 行列带 ICCS 坐标 */
static void print_board(char board[10][9])
{
    static const char *DISP[14] = {
        "帅","仕","相","马","车","炮","兵",
        "將","士","象","馬","車","砲","卒"
    };
    int r, c;
    printf("    a  b  c  d  e  f  g  h  i\n");
    for(r = 0; r < 10; r++)
    {
        printf(" %d  ", 9 - r);
        for(c = 0; c < 9; c++)
        {
            char ch = board[r][c];
            printf("%s ", ch ? DISP[chess_id(ch)] : "＋");
        }
        printf("\n");
        if(r == 4) printf("   ~~~~~~~~ 楚 河 漢 界 ~~~~~~~~\n");
    }
}

/* 在 entry[nCount] 中查找走法, 返回下标或 -1 */
static int find_in_book(book_entry_t *entry, int nCount, unsigned __int16 mv)
{
    int i;
    for(i = 0; i < nCount; i++)
        if(entry[i].move == mv) return i;
    return -1;
}

/* 打印当前局面的在谱分叉(简明列表) */
static void print_branches(char board[10][9], book_entry_t *entry, int nCount, int played)
{
    int i;
    if(nCount == 0) return;
    printf("   分叉(%d): ", nCount);
    for(i = 0; i < nCount; i++)
    {
        char cn[32];
        if(i == played) continue;
        move_cn(board, entry[i].move, cn);
        printf("%s(%d)%s", cn, entry[i].score, entry[i].valid ? "" : "*");
        if(i < nCount - 1) printf(" ");
        if(i >= 7 && nCount > 9) { printf("..."); break; }
    }
    printf("\n");
}

/* 执行一步: 解析输入 -> 查书 -> 打印结果 -> 落子。返回 0 继续, 1 停止 */
static int play_step(char board[10][9], int red, int step, const char *input, int *out_of_book)
{
    unsigned __int16 mv;
    book_entry_t entry[128];
    unsigned __int64 key;
    int nCount, bi;
    char cn[32], ic[16];

    if(!parse_move(board, red, input, &mv))
    {
        printf("第 %d 步: 无法识别着法 \"%s\", 跟踪结束\n", step, input);
        return 1;
    }
    key = board_to_key(board, red);
    nCount = GetBookEntry(entry, key);
    qsort(entry, nCount, sizeof(book_entry_t), cmp_entry);
    bi = find_in_book(entry, nCount, mv);
    move_cn(board, mv, cn);
    move_iccs(mv, ic);

    if(*out_of_book)
    {
        printf("第 %d 步 %s: %s %s  [已出谱]\n", step, red ? "红" : "黑", cn, ic);
    }
    else if(nCount == 0)
    {
        printf("第 %d 步 %s: %s %s  [到边界] 当前局面不在开局库, 此后脱谱\n",
               step, red ? "红" : "黑", cn, ic);
        *out_of_book = 1;
    }
    else if(bi >= 0)
    {
        printf("第 %d 步 %s: %s %s  [在谱] 评分%d 胜%d 和%d 负%d%s\n",
               step, red ? "红" : "黑", cn, ic,
               entry[bi].score, entry[bi].win_count, entry[bi].draw_count,
               entry[bi].lost_count, entry[bi].valid ? "" : " (被禁)");
        print_branches(board, entry, nCount, bi);
    }
    else
    {
        printf("第 %d 步 %s: %s %s  [脱谱] 库中无此着法, 此后脱谱\n",
               step, red ? "红" : "黑", cn, ic);
        print_branches(board, entry, nCount, -1);
        *out_of_book = 1;
    }
    apply_move(board, mv);
    print_board(board);
    return 0;
}

static void play_mode(int nmv, char **moves)
{
    char board[10][9];
    int red, step = 1, i, oob = 0;
    book_entry_t entry[128];
    int nCount;

    if(sqlite3_open(book_path, &db) != SQLITE_OK)
    {
        printf("无法打开 %s\n", book_path);
        return;
    }
    red = fen_to_board(START_FEN, board);
    printf("=== 分叉跟踪(从初始局面) ===\n");
    print_board(board);

    if(nmv > 0)  /* 一次性模式: 参数即着法序列 */
    {
        for(i = 0; i < nmv; i++)
        {
            if(play_step(board, red, step++, moves[i], &oob)) break;
            red = !red;
        }
        /* 结尾打印当前局面的分叉 */
        if(!oob)
        {
            nCount = GetBookEntry(entry, board_to_key(board, red));
            qsort(entry, nCount, sizeof(book_entry_t), cmp_entry);
            printf("--- 当前轮到%s, ", red ? "红" : "黑");
            print_branches(board, entry, nCount, -1);
        }
    }
    else  /* 交互模式 */
    {
        static char hist[512][90];   /* 每步前的棋盘快照, 用于回退 */
        static int hist_oob[512];
        int hn = 0;
        for(;;)
        {
            char line[256], u8[512];
            nCount = GetBookEntry(entry, board_to_key(board, red));
            qsort(entry, nCount, sizeof(book_entry_t), cmp_entry);
            printf("第 %d 步 %s走子%s (b=回退 q=退出)\n", step, red ? "红" : "黑",
                   oob ? " (已脱谱)" : "");
            if(!oob) print_branches(board, entry, nCount, -1);
            printf("> ");
            if(!fgets(line, sizeof(line), stdin)) break;
            line[strcspn(line, "\r\n")] = 0;
            to_utf8(line, u8, sizeof(u8));
            if(!u8[0] || !strcmp(u8, "q") || !strcmp(u8, "quit")) break;
            if(!strcmp(u8, "b") || !strcmp(u8, "back"))  /* 回退一步 */
            {
                if(hn > 0)
                {
                    hn--;
                    memcpy(board, hist[hn], 90);
                    oob = hist_oob[hn];
                    red = !red;
                    step--;
                    printf("已回退到第 %d 步 %s走子:\n", step, red ? "红" : "黑");
                    print_board(board);
                }
                else
                    printf("已经是初始局面, 无法回退\n");
                continue;
            }
            /* 落子前保存快照 */
            if(hn < 512)
            {
                memcpy(hist[hn], board, 90);
                hist_oob[hn] = oob;
                hn++;
            }
            if(play_step(board, red, step++, u8, &oob)) break;
            red = !red;
        }
    }
    sqlite3_close(db);
    fflush(stdout);
    /* tcc 0.9.27 CRT 在特定代码路径下 exit 清理时会崩溃, 输出已刷新, 直接退出 */
    _exit(0);
}

static int check_book_file(const char *path)
{
    sqlite3 *check_db = NULL;
    sqlite3_stmt *stmt = NULL;
    int rc, quick_rows = 0, valid = 0;

    printf("检查文件: %s\n", path);
    rc = sqlite3_open_v2(path, &check_db, SQLITE_OPEN_READONLY, NULL);
    if(rc != SQLITE_OK)
    {
        printf("检查结果: 不合法 (无法打开: %s)\n",
               check_db ? sqlite3_errmsg(check_db) : "未知错误");
        goto done;
    }

    rc = sqlite3_prepare_v2(check_db, "PRAGMA quick_check;", -1, &stmt, NULL);
    if(rc != SQLITE_OK)
    {
        printf("检查结果: 不合法 (%s)\n", sqlite3_errmsg(check_db));
        goto done;
    }
    while((rc = sqlite3_step(stmt)) == SQLITE_ROW)
    {
        const unsigned char *result = sqlite3_column_text(stmt, 0);
        quick_rows++;
        if(!result || strcmp((const char*)result, "ok"))
        {
            printf("检查结果: 不合法 (%s)\n",
                   result ? (const char*)result : "quick_check 未返回结果");
            goto done;
        }
    }
    if(rc != SQLITE_DONE || quick_rows != 1)
    {
        printf("检查结果: 不合法 (%s)\n", sqlite3_errmsg(check_db));
        goto done;
    }
    sqlite3_finalize(stmt);
    stmt = NULL;

    rc = sqlite3_prepare_v2(check_db,
        "SELECT vkey,vmove,vscore,vwin,vdraw,vlost,vvalid,vmemo FROM bhobk LIMIT 0;",
        -1, &stmt, NULL);
    if(rc != SQLITE_OK)
    {
        printf("检查结果: 不合法 (bhobk 表或必需字段缺失: %s)\n",
               sqlite3_errmsg(check_db));
        goto done;
    }

    printf("检查结果: 合法\n");
    printf("SQLite 快速检查及 bhobk 表必需字段检查均通过。\n");
    valid = 1;

done:
    sqlite3_finalize(stmt);
    if(check_db) sqlite3_close(check_db);
    return valid ? 0 : 1;
}

static void print_help(void)
{
    printf("OBK 象棋开局库查询工具\n\n");
    printf("用法:\n");
    printf("  bhobk.exe                   查询初始局面\n");
    printf("  bhobk.exe <FEN>             查询指定局面(FEN 含空格需加引号)\n");
    printf("  bhobk.exe --key <vkey>      直接按 vkey 查询\n");
    printf("  bhobk.exe --demo            查询演示 key\n");
    printf("  bhobk.exe --play [着法...]  分叉跟踪; 无着法时进入交互模式\n");
    printf("  bhobk.exe --db <文件>       指定开局库(默认 test.obk)\n");
    printf("  bhobk.exe --check           快速检查开局库是否合法\n");
    printf("  bhobk.exe -h, --help        显示此帮助\n\n");
    printf("--db 和 --check 需放在其他查询参数之前。\n");
    printf("着法支持中文或 ICCS 坐标(如 炮二平五、h2-e2)。\n");
    printf("交互模式: b=回退一步, 空行/q=退出。\n");
}

int main(int argc, char **argv)
{
    book_entry_t entry[128];
    int nCount, i;
    int argi = 1, check_only = 0;
    unsigned __int64 key ;
    char board[10][9];
    int have_board = 0, red_to_move = 1;
    char fen[512] = {0};
    char db_path_arg[512];
    char *moves_ptr[128];

#ifdef _WIN32
    SetConsoleOutputCP(65001);  /* 控制台按 UTF-8 输出 */
#endif

    memset(entry, 0, sizeof(entry));

    while(argi < argc)
    {
        if(!strcmp(argv[argi], "--db"))
        {
            if(argi + 1 >= argc)
            {
                printf("--db 需要指定 .obk 文件名。\n");
                return 1;
            }
            to_utf8(argv[argi + 1], db_path_arg, sizeof(db_path_arg));
            book_path = db_path_arg;
            argi += 2;
        }
        else if(!strcmp(argv[argi], "--check"))
        {
            check_only = 1;
            argi++;
        }
        else
            break;
    }

    if(argi > 1)
    {
        for(i = 1; argi < argc; i++, argi++)
            argv[i] = argv[argi];
        argc = i;
    }

    if(argc > 1 && (!strcmp(argv[1], "-h") || !strcmp(argv[1], "--help")))
    {
        print_help();
        return 0;
    }

    if(check_only)
    {
        if(argc != 1)
        {
            printf("--check 不能与其他查询参数同时使用。\n");
            return 1;
        }
        return check_book_file(book_path);
    }

    if(argc == 1)
        printf("提示: 使用 -h 或 --help 查看命令行帮助。\n\n");

    if(argc > 1 && !strcmp(argv[1], "--play"))
    {
        /* Windows 控制台传入的中文参数是 GBK, 统一转 UTF-8 */
        static char u8args[128][512];
        int nmv = argc - 2, i;
        if(nmv > 128) nmv = 128;
        for(i = 0; i < nmv; i++)
        {
            to_utf8(argv[2 + i], u8args[i], 512);
            moves_ptr[i] = u8args[i];
        }
        play_mode(nmv, moves_ptr);
        return 0;
    }

    if(argc > 1 && !strcmp(argv[1], "--demo"))
    {
        key = 15265892774299731920ULL;
    }
    else if(argc > 2 && !strcmp(argv[1], "--key"))
    {
        sscanf(argv[2], "%I64u", &key);
    }
    else if(argc > 1 && argv[1][0] >= '0' && argv[1][0] <= '9')
    {
        sscanf(argv[1], "%I64u", &key);
    }
    else
    {
        /* 无参数用初始局面; 有参数按 FEN 处理(多个参数按空格拼接) */
        if(argc == 1)
            strcpy(fen, START_FEN);
        else
        {
            for(i = 1; i < argc; i++)
            {
                if(i > 1) strcat(fen, " ");
                strcat(fen, argv[i]);
            }
        }
        red_to_move = fen_to_board(fen, board);
        if(red_to_move < 0)
        {
            printf("FEN 解析失败: %s\n", fen);
            return 1;
        }
        key = board_to_key(board, red_to_move);
        have_board = 1;
        printf("FEN: %s\n", fen);
        printf("走子方: %s\n", red_to_move ? "红" : "黑");
        print_board(board);
    }

    if(sqlite3_open(book_path, &db) != SQLITE_OK)
    {
        printf("无法打开 %s\n", book_path);
        return 1;
    }

    nCount = GetBookEntry(entry, key);
    sqlite3_close(db);

    printf("vkey: %I64u\n", key);
    printf("命中 %d 条开局库着法:\n\n", nCount);
    if(nCount == 0)
    {
        printf("  (库中无此局面)\n");
        return 0;
    }
    qsort(entry, nCount, sizeof(book_entry_t), cmp_entry);
    print_pad("着法", 12); print_pad("ICCS", 9);
    printf("%6s %4s %4s %4s %4s  %s\n", "评分", "胜", "和", "负", "有效", "备注");
    for(i = 0; i < nCount; i++)
    {
        char cn[32], ic[16], memo[256];
        if(have_board)
        {
            move_cn(board, entry[i].move, cn);
            move_iccs(entry[i].move, ic);
        }
        else
        {
            sprintf(cn, "<move=%u>", entry[i].move);
            ic[0] = 0;
        }
        memo_utf8(entry[i].comments, memo, sizeof(memo));
        print_pad(cn, 12); print_pad(ic, 9);
        printf("%6d %4d %4d %4d %4d  %s\n",
               entry[i].score, entry[i].win_count, entry[i].draw_count,
               entry[i].lost_count, entry[i].valid, memo);
    }
    return 0 ;
}
