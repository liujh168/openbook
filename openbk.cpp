#include <stdio.h>
#include <mem.h>
#include <stdlib.h>

#include <iostream>
#include <fstream>
#include <vector>
#include <iterator>
#include<algorithm>

#include "openbk.h"

using namespace std;

template<class charT, class traits>
basic_istream<charT, traits> & operator >>(basic_istream<charT, traits> & in, const Entry & x)
{
    in.read((char *)(Entry *)&x, sizeof(Entry));
    return in;
}

template<class charT, class traits>
basic_ostream<charT, traits> & operator<<(basic_ostream<charT, traits> & out, const Entry & x)
{
    out.write((char *)(Entry *)&x, sizeof(Entry));
    return out;
}

bool Entry::operator == (const Entry& obj)
{
        return ( key == obj.key && move == obj.move);
}

bool Entry::operator <(const Entry& obj) const
{
	return key < obj.key ;
}

bool Entry::operator >(const Entry& obj) const
{
	return key > obj.key ;
}

COpenBook::COpenBook(char *fileout)
{
        //从原始开局库文件中读出数据
     ifstream infile(fileout, std::ios_base::binary);
     if(!infile)
     {
        cout<<"open error!" <<endl;
        return ;
     }

        //std::cout<<"打开开局库文件： " << fileout << std::endl;

        infile.clear();
        infile.seekg(0, ios::end); // Move pointer to end, so tellg() gets file's size
        size_t iEntry = (size_t)infile.tellg() / sizeof(Entry) - 1;   //原始开局库中有多少个局面，注意从0开始。

        vector<Entry> book(iEntry);
        vector<Entry>::iterator it;

        infile.clear();
        infile.seekg(0, ios::beg);             //move pointer to begin
        for(it=book.begin();it!=book.end();it++)
        {
                infile.read((char*)it, sizeof(Entry));
                //*it = e;
        }

        infile.close();

        book_e = book;
     return ;
}

COpenBook::~COpenBook()
{


}

bool COpenBook::WriteToBook(char *fileout)
{
        //排序vector
        sort(book_e.begin(),book_e.end(),less<Entry>());

        //写入文件
         ofstream ofs(fileout, ios_base::binary);
         copy(book_e.begin(), book_e.end(),  ostream_iterator <Entry>(ofs));    //方法1：一次性写入

       //for(vector<Entry>::iterator iter = book_e.begin();iter != book_e.end(); ++iter)
       //{
       //      ofs.write( (char*) iter, sizeof(Entry ));       //方法2：逐个写入
       //}

      ofs.close();
      return true;
}

bool COpenBook::PutInMove( void )
{
           int x;
           //bool exist = false ;
           CChessMove tempmove, move;
           unsigned char tempchar1,tempchar2, tempposition[256];
           Entry e;

           totals++;    //总局面数量

           memcpy( tempposition ,m_Position,256);

           move = m_StepRecords[m_TotalSteps];

            //1、find if already exist?
           LeftToRight(tempposition);
           tempmove.m_From = (move.m_From & 0xf0) | (0x0c-(move.m_From &0x0f)+0x02);
           tempmove.m_To =   (move.m_To   & 0xf0) | (0x0c-(move.m_To   &0x0f)+0x02);
           e.key = CalcIndexAndKey(tempposition);
           e.move = tempmove.m_From<<8|tempmove.m_To;
           if ( !(find(book_e.begin(), book_e.end(), e) == book_e.end()) )
           {
                 //exist =true;
                 duicheng++;
                 return  false;
           }

           ChangeSide(tempposition);
           tempmove.m_From = 0xdc-tempmove.m_From+0x22;
           tempmove.m_To = 0xdc-tempmove.m_To+0x22;
           e.key = CalcIndexAndKey(tempposition);
           e.move = tempmove.m_From<<8|tempmove.m_To;
           if ( !(find(book_e.begin(), book_e.end(), e) == book_e.end()) )
           {
                 //exist =true;
                 duicheng++;
                 return  false;
           }

           LeftToRight(tempposition);
           tempmove.m_From = (tempmove.m_From & 0xf0) | (0x0c-(tempmove.m_From &0x0f)+0x02);
           tempmove.m_To = (tempmove.m_To & 0xf0) | (0x0c-(tempmove.m_To &0x0f)+0x02);
           e.key = CalcIndexAndKey(tempposition);;
           e.move = tempmove.m_From<<8|tempmove.m_To;
           if ( !(find(book_e.begin(), book_e.end(), e) == book_e.end()) )
           {
                 //exist =true;
                 duicheng++;
                 return  false;
           }

           //没有找到对称局面时
           e.key = m_HashKey64;
           e.move = move.m_From<<8|move.m_To;
           e.count = 1;
           e.learn = 1;

           if ( !(find(book_e.begin(), book_e.end(), e) == book_e.end()) )
           {
                repeat++;
           }
           else 
           {
                book_e.push_back(e);
                join++;
           }

           return true;
}

bool COpenBook::DataClear(void)
{
     book_e.clear();
     return true;
}


//基于文件的外部排序算法都需要合并两个有序的文件.
//其中的数据类型可以参数化，本函数做成函数模板也可以
bool    COpenBook::merge_file(char* file_in_name1, char* file_in_name2, char* file_out_name)
{
	//打开两个输入文件和一个输出文件
	ifstream fin1,fin2;
	fin1.open(file_in_name1,ios::in | ios::binary);
	fin2.open(file_in_name2,ios::in | ios::binary);

	ofstream fout;
	fout.open(file_out_name,ios::out | ios::binary);
	//在每个文件中先各读出第一个数

	bool bin1=fin1.is_open();
	bool bin2=fin2.is_open();
	bool bin3=fout.is_open();
	if(!(bin1&bin2&bin3) )
	{
		return false;
	}

	Entry temp1,temp2;
	fin1.read(reinterpret_cast<char*>(&temp1),sizeof(Entry));
	fin2.read(reinterpret_cast<char*>(&temp2),sizeof(Entry));

	//在两个文件中前进，每次只选择两个文件中较小的那个数添加到输出文件的末尾
	while (true)
	{
		if (temp1<temp2)
		{
			fout.write(reinterpret_cast<const char*>(&temp1),sizeof(Entry));
			//到文件的最后一个数读完之后，再读一次，保证每个文件中的所有数据都被读到。
			fin1.read(reinterpret_cast<char*>(&temp1),sizeof(Entry));
			if (fin1.eof())
			{
				break;
			}
		}
		else
		{
			fout.write(reinterpret_cast<const char*>(&temp2),sizeof(Entry));
			fin2.read(reinterpret_cast<char*>(&temp2),sizeof(Entry));
			if (fin2.eof())
			{
				break;
			}
		}
	}

	if (!fin1.eof())
	{
		while (true)
		{
			//另一个文件已经读完了，说明当前这个文件中最后读到的那个整数还没有被写出，所以要先写出。
			fout.write(reinterpret_cast<const char*>(&temp1),sizeof(Entry));
			fin1.read(reinterpret_cast<char*>(&temp1),sizeof(Entry));
			if (fin1.eof())
			{
				break;;
			}
		}
	}
	else
		while (true)
		{
			fout.write(reinterpret_cast<const char*>(&temp2),sizeof(Entry));
			fin2.read(reinterpret_cast<char*>(&temp2),sizeof(Entry));
			if (fin2.eof())
			{
				break;
			}
		}
	fin1.close();
	fin2.close();
	fout.close();
        return true;
}

bool COpenBook::copy_file(char* dst, char* src)
{
    ifstream fin(src,ios::in|ios::binary);
    if(!fin){
            return false;
    }
    ofstream fout(dst,ios::out|ios::binary);
    if(!fout){
            return false;
    }

    char c[1024];
    while(!fin.eof())
    {
        fin.read(c,1024);
        fout.write(c,fin.gcount());
    }

    fin.close();
    fout.close();
    return true;
}

bool COpenBook::del_repeat(char *file_in_name1)
{
        vector<Entry> book;
        vector<Entry>::iterator it;

	ifstream fin1;
	ofstream fout;
	fin1.open(file_in_name1, ios::in | ios::binary);
	fout.open("合并去重.bin", ios::out | ios::binary);
 	bool bin1=fin1.is_open();
	bool bin3=fout.is_open();
	if(!(bin1&bin3)){
		return false;
	}

	Entry temp1;

        totals = 0;
        repeat = 0;
        join = 0;

	while (!fin1.eof())
	{
           totals++;

           fin1.read(reinterpret_cast<char*>(&temp1),sizeof(Entry));
           if (find(book.begin(), book.end(), temp1) == book.end())
           {
                book.push_back(temp1);
                join++;
           }
           else
           {
                repeat++;
           }

	}

        for(it=book.begin();it!=book.end();it++)
        {
               fout.write((char*)it, sizeof(Entry));
        }

        fin1.close();
        fout.close();
        return true;
}

