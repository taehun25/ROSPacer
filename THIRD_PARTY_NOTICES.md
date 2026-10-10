# Third-party reference files

ROSPacer의 Python 구현과 별도로, `reference/`에는 생성 XML을 확인하기 위한 벤더 XSD를 보관합니다.
이 파일은 ROSPacer가 개발한 미들웨어 구현이 아니며, 각 원본의 라이선스를 따릅니다.
정확한 출처 URL과 LF로 저장한 파일의 SHA-256은 `reference/SOURCES.json`에 있습니다.

## eProsima Fast DDS

- 원본 저장소: https://github.com/eProsima/Fast-DDS
- 원본 파일: `resources/xsd/fastRTPS_profiles.xsd`
- 포함 버전: `v2.6.9`, `v2.6.10`, `v2.6.11`
- 원본 라이선스: Apache License 2.0. 사본: [reference/fastdds-LICENSE](reference/fastdds-LICENSE).

`fastdds-2.6.10-local-validation.xsd`는 v2.6.10 원본에 다음 변경을 적용한 검증용 사본입니다.

1. 미정의 `int32` type 참조를 원본에 정의된 `int32Type`으로 바꿉니다.
2. 미정의 `uint32` type 참조를 `uint32Type`으로 바꿉니다.
3. 미정의 `uint64` type 참조를 `xs:unsignedLong`으로 바꿉니다.
4. `userTransports`의 목록 타입을 분리하여 child 이름을 `id` 대신 `transport_id`로 맞춥니다.

4번은 실제 v2.6.10의 [XMLElementParser.cpp](https://github.com/eProsima/Fast-DDS/blob/v2.6.10/src/cpp/rtps/xmlparser/XMLElementParser.cpp)의
`getXMLTransports` 동작과 대응시킨 것입니다. 원본 XSD는 그대로 함께 보관합니다.
이 수정 사본의 검증 결과를 수정하지 않은 공식 XSD 검증 결과로 표시하지 않습니다.
이 변경은 vendor 라이브러리나 DDS 실행 코드를 수정하지 않습니다.

## Eclipse Cyclone DDS

- 원본 저장소: https://github.com/eclipse-cyclonedds/cyclonedds
- 원본 파일: `etc/cyclonedds.xsd`
- 포함 버전: `0.10.4`, `0.10.5`
- 원본 라이선스와 attribution: [reference/cyclonedds-LICENSE](reference/cyclonedds-LICENSE),
  [reference/cyclonedds-NOTICE.md](reference/cyclonedds-NOTICE.md).

Cyclone DDS XSD의 기능 변경은 하지 않았습니다. 저장소의 text 파일은 LF로 저장하며 NOTICE의 끝 빈 줄만 정리했습니다.
생성 XML의 스키마 검사 성공과 실제 Cyclone DDS parser 성공은 별도로 확인해야 합니다.

## 배포 범위

개발 중 조회한 벤더 parser `.cpp` 사본은 로컬 참고 자료로만 유지하며 Git에서 제외합니다.
코드 위치와 원본 링크는 위에서 제공합니다. 실험 원시 로그, 개인 SSH key와 Python/build 캐시는 포함하지 않습니다.
ROSPacer 자체 코드의 라이선스는 아직 지정하지 않았으며 위 원본 라이선스가 ROSPacer 전체에 자동 적용되는 것은 아닙니다.
