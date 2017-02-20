
//---------------------------------------------------------------------------

#ifndef BookFormH
#define BookFormH
//---------------------------------------------------------------------------
#include <Classes.hpp>
#include <Controls.hpp>
#include <StdCtrls.hpp>
#include <Forms.hpp>
#include <Buttons.hpp>
#include <Dialogs.hpp>
#include <Grids.hpp>
#include <OleCtrls.hpp>
#include <StdCtrls.hpp>
#include <ComCtrls.hpp>

#include "CBLibXControl_OCX.h"
#include "openbk.h"
#include <ImgList.hpp>
#include <ExtCtrls.hpp>
#include <Graphics.hpp>


//---------------------------------------------------------------------------
class Tfrmbook : public TForm
{
__published:	// IDE-managed Components
        TLabel *lbl1;
        TButton *btnMake;
        TButton *btnLib;
        TMemo *Memo1;
        TListBox *ListBox1;
        TStringGrid *StringGrid1;
        TCBLibX *CBLibX1;
        TOpenDialog *dlgOpen1;
        TOpenDialog *OpenDialog1;
        TMemo *mmo1;
        TTreeView *treeView1;
        TCheckBox *chkdel;
        TEdit *edtDest;
        TEdit *edtSource;
        TButton *Button1;
        TButton *Button2;
        TButton *btn1;
        TButton *Button3;
        TEdit *edtCalced;
        TLabel *lblCalced;
        TImageList *il1;
        TImage *imgboard;
        TLabel *Label1;
        TButton *btnMerge;
        void __fastcall btnMakeClick(TObject *Sender);
        void __fastcall btnLibClick(TObject *Sender);
        void __fastcall ListBox1DblClick(TObject *Sender);
        void __fastcall FormCreate(TObject *Sender);
        void __fastcall FormDestroy(TObject *Sender);
        void __fastcall Button1Click(TObject *Sender);
        void __fastcall Button2Click(TObject *Sender);
        void __fastcall btn1Click(TObject *Sender);
        void __fastcall Button3Click(TObject *Sender);
        void __fastcall edtCalcedChange(TObject *Sender);
        void __fastcall chkdelClick(TObject *Sender);
        void __fastcall btnMergeClick(TObject *Sender);

private:

        COpenBook ob;
        TTreeNode *curNode;

        unsigned long long iCountCBL, iCountQiPu, iCountJuMian ;
        int iCalced;            //处理的半回合数

        bool QiPu2Tree(char * qipan ,bool redfirst, AnsiString qipu);	// User declarations
        bool ScanNode(TTreeNode *node);
        void OpenCBL(char * filename);
        void QiPuInfo(int qipuno);

        void DisplayCBL(void);
        void DisplayQiPu(void);
        void PrintBoard(void);
        void drawiconboard(unsigned char cposition[256]);

public:		// User declarations
        __fastcall Tfrmbook(TComponent* Owner);
};
//---------------------------------------------------------------------------
extern PACKAGE Tfrmbook *frmbook;
//---------------------------------------------------------------------------
#endif
