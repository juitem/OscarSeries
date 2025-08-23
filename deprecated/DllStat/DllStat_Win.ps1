# 스크립트가 실행될 때, old dir과 new dir 경로를 인자로 받거나, 직접 지정할 수 있도록 합니다.
# 예제에서는 변수로 직접 지정하겠습니다.
$oldDir = "C:\path\to\your\old\dir"
$newDir = "C:\path\to\your\new\dir"

# 결과를 저장할 해시 테이블 초기화
$oldDirSectionSums = @{}
$newDirSectionSums = @{}

# 두 디렉토리를 처리하는 함수 정의
function Get-SectionSums($directory, $sumsTable) {
    Write-Host "Processing directory: $directory" -ForegroundColor Green

    # 해당 디렉토리와 하위 디렉토리의 모든 DLL 파일 찾기
    $dllFiles = Get-ChildItem -Path $directory -Filter "*.dll" -Recurse

    foreach ($file in $dllFiles) {
        try {
            $stream = New-Object System.IO.FileStream($file.FullName, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read)
            $reader = New-Object System.IO.BinaryReader($stream)

            # DOS 헤더 스킵
            $reader.ReadBytes(60)
            $peHeaderOffset = $reader.ReadUInt32()
            $stream.Seek($peHeaderOffset, [System.IO.SeekOrigin]::Begin)

            # PE Signature
            if ($reader.ReadUInt32() -ne 0x00004550) { # "PE\0\0"
                Write-Host "Skipping non-PE file: $($file.Name)" -ForegroundColor Yellow
                $reader.Dispose()
                $stream.Dispose()
                continue
            }

            # File Header
            $machine = $reader.ReadUInt16()
            $numberOfSections = $reader.ReadUInt16()
            $timeDateStamp = $reader.ReadUInt32()
            $pointerToSymbolTable = $reader.ReadUInt32()
            $numberOfSymbols = $reader.ReadUInt32()
            $sizeOfOptionalHeader = $reader.ReadUInt16()
            $characteristics = $reader.ReadUInt16()

            # Optional Header (Optional Header의 크기만큼 읽어서 다음 위치로 이동)
            $reader.ReadBytes($sizeOfOptionalHeader)

            # Section Headers
            for ($i = 0; $i -lt $numberOfSections; $i++) {
                $nameBytes = $reader.ReadBytes(8)
                $sectionName = [System.Text.Encoding]::ASCII.GetString($nameBytes).Trim([char]0)
                $virtualSize = $reader.ReadUInt32()
                $virtualAddress = $reader.ReadUInt32()
                $sizeOfRawData = $reader.ReadUInt32()
                $pointerToRawData = $reader.ReadUInt32()
                $pointerToRelocations = $reader.ReadUInt32()
                $pointerToLinenumbers = $reader.ReadUInt32()
                $numberOfRelocations = $reader.ReadUInt16()
                $numberOfLinenumbers = $reader.ReadUInt16()
                $characteristics = $reader.ReadUInt32()

                # 섹션 크기 누적
                if ($sumsTable.ContainsKey($sectionName)) {
                    $sumsTable[$sectionName] += $sizeOfRawData
                } else {
                    $sumsTable[$sectionName] = $sizeOfRawData
                }
            }
        } catch {
            Write-Host "Error processing file $($file.FullName): $_" -ForegroundColor Red
        } finally {
            if ($reader) { $reader.Dispose() }
            if ($stream) { $stream.Dispose() }
        }
    }
}

# 함수 호출
Get-SectionSums -directory $oldDir -sumsTable $oldDirSectionSums
Get-SectionSums -directory $newDir -sumsTable $newDirSectionSums

# 결과 출력
Write-Host "`n=========================================="
Write-Host "    Old Directory Section Sums" -ForegroundColor Cyan
Write-Host "=========================================="
$oldDirSectionSums.GetEnumerator() | Sort-Object Name | Format-Table -AutoSize

Write-Host "`n=========================================="
Write-Host "    New Directory Section Sums" -ForegroundColor Cyan
Write-Host "=========================================="
$newDirSectionSums.GetEnumerator() | Sort-Object Name | Format-Table -AutoSize

Write-Host "`n=========================================="
Write-Host "    Comparison (New vs Old)" -ForegroundColor Cyan
Write-Host "=========================================="
Write-Host "Section Name`t`tOld Total`t`tNew Total`t`tDifference"

$allSections = ($oldDirSectionSums.Keys + $newDirSectionSums.Keys) | Sort-Object -Unique

foreach ($section in $allSections) {
    $oldSum = $oldDirSectionSums[$section]
    $newSum = $newDirSectionSums[$section]

    if (-not $oldSum) { $oldSum = 0 }
    if (-not $newSum) { $newSum = 0 }

    $difference = $newSum - $oldSum
    
    # 출력 포맷팅을 위해 PadRight를 사용
    $sectionNamePadded = $section.PadRight(15)
    $oldSumPadded = $oldSum.ToString().PadLeft(12)
    $newSumPadded = $newSum.ToString().PadLeft(12)
    $differencePadded = $difference.ToString().PadLeft(12)

    Write-Host "$sectionNamePadded$oldSumPadded`t$newSumPadded`t$differencePadded"
}