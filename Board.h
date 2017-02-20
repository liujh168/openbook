#ifndef BOARD_H
#define BOARD_H

typedef unsigned __int16 uint16_t;
typedef unsigned __int32 uint32_t;
typedef unsigned __int64 uint64_t;
typedef unsigned __int64 Key64;

const unsigned char NOCHESS     = 0 ;
const unsigned char B_KING      = 1;  //黑帅        15-  B_KING = 14
const unsigned char B_ROOK      = 2;  //黑车                      13
const unsigned char B_HORSE     = 3;  //黑马                      12
const unsigned char B_CANNON     = 4;  //黑炮                     11
const unsigned char B_BISHOP    = 5 ; //黑士                      10
const unsigned char B_ELEPHANT  = 6 ; //黑象                      9
const unsigned char B_PAWN      = 7 ; //黑卒                      8

const unsigned char R_KING      = 8;   //红帅         15- R_KING =7
const unsigned char R_ROOK       = 9;   //红车                    6
const unsigned char R_HORSE      =10;  //红马                     5
const unsigned char R_CANNON    =  11;  //红炮                    4
const unsigned char R_BISHOP    = 12;  //红士                     3
const unsigned char R_ELEPHANT  = 13;  //红象                     2
const unsigned char R_PAWN      = 14;  //红兵                     1

#define IsBlack(x)   (x>=B_KING&&x<=B_PAWN)
#define IsRed(x)     (x>=R_KING&&x<=R_PAWN)

//着法类，描述了一种着法的提址、落址、吃子
struct CChessMove
{
    unsigned char       m_From;            //提址（用16*16表示法）
    unsigned char       m_To;              //落址（用16*16表示法）
   // unsigned char       m_KillID;          //吃子（用 enum Chessman 表示）
};

class CBoard
{
const static int MAXTOTALSTEPS      = 500;

public:
    CBoard();

    unsigned char       MakeMove(CChessMove* move);
    void                UnMakeMove(CChessMove* move,unsigned char killid);
    void                ChangeSide(unsigned char m_position[256]);
    void                LeftToRight(unsigned char m_position[256]);
    Key64               CalcIndexAndKey(unsigned char CurPosition[256]);

    unsigned char       m_Position[256];
    bool                m_Player;
    unsigned int        m_TotalSteps;
    CChessMove          m_StepRecords[MAXTOTALSTEPS];
    Key64               m_HashKey64;

private:
    void        Print(void);

    Key64       m_zobSideToMove;
    Key64       m_ulHashKey64[15][256];
};


#endif
