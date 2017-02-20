功能：

    1、从象棋桥棋谱格式文件（2.x）转换生成"橘中新趣"引擎可用的开局库.
    
    2、增加合并开局库功能
    
用法：

    1、准备好象棋桥棋谱格式文件（2.x）若干。
    
    3、运行本软件
    
    4、点击“选择棋库”选择准备好的棋谱文件
    
    5、点击“开始转换”即可生成开局库文件。
    
注意：

    1、如棋谱文件与本软件在同一目录，直接点击"开始转换" 即可立即转换全部棋谱。
    
    2、本软仅支持2.x版本的象棋桥棋谱格式文件，如版本不对，请先用象棋桥本身提供的，转换功能转换成2.x版本的棋谱文件。
    
    3、如勾选了"清除旧开局"，则旧开局库被覆盖
    
    4、开局库缺省名为"book.bin",可自行更名

版本历史：

2017年元旦增加合并开局库功能,1月11日去掉了重新局面。

2016年12月24日

    平安夜搞定开局库生成工具。主要修订有：
    
    1、去掉 board.h 中的 Key32 那个变量及相关的数组。
    
    2、生成找开局库文件名缺省更改为“book.bin”，原来是“openbook.dat”，且生成的文件中不再保存随机数表。
    
    3、删除了多余的代码，梳理精简了逻辑, 可以保留旧开局库文件中的数据。

2016年以前旧版废弃了
