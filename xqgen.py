# -*- coding: utf-8 -*-
"""xqgen.py — 精简象棋走法生成(伪合法,开局验证够用)"""
def gen_moves(board, red):
    """board: {(r,c):ch}; red: 当前走子方。产出 (fr,fc,tr,tc)"""
    moves = []
    for (r, c), ch in list(board.items()):
        if ch.isupper() != red:
            continue
        t = ch.upper()
        tgt = board.get
        if t == 'P':
            fwd = -1 if red else 1
            for dr, dc in [(fwd, 0)] + ([(0, 1), (0, -1)] if ((r <= 4) if red else (r >= 5)) else []):
                nr, nc = r + dr, c + dc
                if 0 <= nr <= 9 and 0 <= nc <= 8 and (tgt((nr, nc)) is None or tgt((nr, nc)).isupper() != red):
                    moves.append((r, c, nr, nc))
        elif t == 'K':
            rows = range(7, 10) if red else range(0, 3)
            for dr, dc in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
                nr, nc = r + dr, c + dc
                if nr in rows and 3 <= nc <= 5 and (tgt((nr, nc)) is None or tgt((nr, nc)).isupper() != red):
                    moves.append((r, c, nr, nc))
        elif t == 'A':
            rows = (7, 8, 9) if red else (0, 1, 2)
            for dr, dc in [(1, 1), (1, -1), (-1, 1), (-1, -1)]:
                nr, nc = r + dr, c + dc
                if nr in rows and 3 <= nc <= 5 and (tgt((nr, nc)) is None or tgt((nr, nc)).isupper() != red):
                    moves.append((r, c, nr, nc))
        elif t == 'B':
            rows_ok = (lambda nr: nr >= 5) if red else (lambda nr: nr <= 4)
            for dr, dc in [(2, 2), (2, -2), (-2, 2), (-2, -2)]:
                nr, nc = r + dr, c + dc
                if 0 <= nr <= 9 and 0 <= nc <= 8 and rows_ok(nr) and tgt((r + dr // 2, c + dc // 2)) is None \
                        and (tgt((nr, nc)) is None or tgt((nr, nc)).isupper() != red):
                    moves.append((r, c, nr, nc))
        elif t == 'N':
            for dr, dc, lr, lc in [(2, 1, 1, 0), (2, -1, 1, 0), (-2, 1, -1, 0), (-2, -1, -1, 0),
                                   (1, 2, 0, 1), (1, -2, 0, -1), (-1, 2, 0, 1), (-1, -2, 0, -1)]:
                nr, nc = r + dr, c + dc
                if 0 <= nr <= 9 and 0 <= nc <= 8 and tgt((r + lr, c + lc)) is None \
                        and (tgt((nr, nc)) is None or tgt((nr, nc)).isupper() != red):
                    moves.append((r, c, nr, nc))
        elif t in ('R', 'C'):
            for dr, dc in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
                nr, nc = r + dr, c + dc
                jumped = False
                while 0 <= nr <= 9 and 0 <= nc <= 8:
                    p = tgt((nr, nc))
                    if t == 'R':
                        if p is None:
                            moves.append((r, c, nr, nc))
                        else:
                            if p.isupper() != red:
                                moves.append((r, c, nr, nc))
                            break
                    else:
                        if not jumped:
                            if p is None:
                                moves.append((r, c, nr, nc))
                            else:
                                jumped = True
                        else:
                            if p is not None:
                                if p.isupper() != red:
                                    moves.append((r, c, nr, nc))
                                break
                    nr += dr
                    nc += dc
    return moves

def apply(board, mv):
    fr, fc, tr, tc = mv
    b = dict(board)
    b[(tr, tc)] = b.pop((fr, fc))
    return b
