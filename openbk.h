#ifndef OpenBk_H
#define OpenBk_H

#include <vector>
#include <algorithm>

#include "board.h"

//这是sf50开局库找格式定义
 struct Entry {
    uint64_t key;
    uint16_t move;
    uint16_t count;
    uint32_t learn;
    bool operator == (const Entry& obj);
    bool operator >(const Entry& obj) const;  //降序排列需要重载的操作符
    bool operator <(const Entry& obj) const;  //升序排列需要重载的操作符
  };

class COpenBook : public CBoard
{
public:
	COpenBook(char *fileout="book.bin");
	~COpenBook();

    bool            DataClear(void);
    bool            PutInMove(void);
    bool            WriteToBook(char* fileout);
    static bool     merge_file(char* file_in_name1, char* file_in_name2, char* file_out_name);  //合并排序好找文件
    static bool     copy_file(char* dst, char* src);        //简单的拷贝文件代码。
    bool            del_repeat(char *file_in_name1);             //删除重复局面

    unsigned long       totals;              //总局面数量
    unsigned long       join;                //增加局面数
    unsigned long       repeat;
    unsigned long       duicheng;

private:
    std::vector<Entry> book_e;
};

#endif
