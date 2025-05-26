# 1. BuildFunc가 mybuildfunc인 행 전체(헤더+값) 출력
get_row_by_buildfunc mydata.csv mybuildfunc

# 2. BuildFunc가 mybuildfunc인 행의 GitUrl 값만 출력
get_field_by_buildfunc mydata.csv mybuildfunc GitUrl

# 3. BuildFunc가 mybuildfunc인 행의 SrcRoot와 GitUrl을 수정
update_fields_by_buildfunc mydata.csv mybuildfunc SrcRoot="/root" GitUrl="http://1.org.git"
