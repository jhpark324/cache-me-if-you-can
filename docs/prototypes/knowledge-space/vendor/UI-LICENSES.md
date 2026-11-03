# UI 라이브러리와 런타임 의존성 라이선스

- 추출일: 2026-11-02
- 기준: 이 프리뷰의 `package-lock.json`과 설치된 `node_modules`의 `package.json`·LICENSE·CopyrightNotice 원문.
- 범위: 직접 UI 의존성 4개 및 production 의존성 전체 81개. esbuild와 플랫폼별 빌드 실행 파일 같은 dev 의존성은 포함하지 않는다.
- 번들의 tree shaking으로 제외되는 패키지가 있을 수 있다. 아래 목록은 최종 번들의 코드 포함량을 주장하지 않고 production 의존성의 고지 문구를 함께 보존한다.
- 기존 그래프 라이브러리 고지는 [THIRD-PARTY-LICENSES.md](THIRD-PARTY-LICENSES.md), 폰트 고지는 [자산 인덱스](../assets/index.md)에서 관리한다.

## 추출 방식

동일한 원문을 SHA-256으로 묶어 중복 없이 보존하고, 각 패키지 행이 해당 원문을 가리키게 했다. 저작권 문구가 다른 MIT 원문은 별도 항목이다. `tslib`는 LICENSE와 CopyrightNotice를 모두 보존한다. 패키지 버전이 바뀌면 lockfile 기준으로 다시 추출한다.

`react-remove-scroll-bar@2.3.8`은 설치된 배포 패키지에 LICENSE 파일이 없고 `package.json`에 MIT가 선언되어 있다. 이 패키지의 고지는 공식 저장소의 LICENSE를 고정 커밋에서 보충했다. 이는 npm 패키지에 포함돼 있던 파일로 표시하지 않는다. 원문 출처: [공식 저장소 LICENSE](https://github.com/theKashey/react-remove-scroll-bar/blob/8ca9ba5ea52de03308fe8ced94f7b159a44d28ff/LICENSE).

빌드가 추출한 별도 고지 파일 [app.js.LEGAL.txt](../dist/app.js.LEGAL.txt)도 배포 번들과 함께 보관한다.

## 패키지 목록

| 패키지 | 버전 | 구분 | 선언 라이선스 | 원문 |
| --- | --- | --- | --- | --- |
| `@floating-ui/core` | `1.8.0` | 전이 | `MIT` | [L01](#l01) |
| `@floating-ui/dom` | `1.8.0` | 전이 | `MIT` | [L01](#l01) |
| `@floating-ui/react-dom` | `2.1.9` | 전이 | `MIT` | [L01](#l01) |
| `@floating-ui/utils` | `0.2.12` | 전이 | `MIT` | [L01](#l01) |
| `@radix-ui/colors` | `3.0.0` | 전이 | `MIT` | [L02](#l02) |
| `@radix-ui/number` | `1.1.3` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/primitive` | `1.2.0` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/react-accessible-icon` | `1.2.0` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/react-accordion` | `1.3.1` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/react-alert-dialog` | `1.2.1` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/react-arrow` | `1.1.17` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/react-aspect-ratio` | `1.2.0` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/react-avatar` | `1.3.1` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/react-checkbox` | `1.4.1` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/react-collapsible` | `1.2.1` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/react-collection` | `1.2.0` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/react-compose-refs` | `1.1.5` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/react-context` | `1.3.0` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/react-context-menu` | `2.4.1` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/react-dialog` | `1.3.1` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/react-direction` | `1.2.0` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/react-dismissable-layer` | `1.2.1` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/react-dropdown-menu` | `2.2.1` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/react-focus-guards` | `1.2.0` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/react-focus-scope` | `1.3.1` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/react-form` | `0.3.0` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/react-hover-card` | `1.2.1` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/react-id` | `1.1.4` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/react-label` | `2.1.17` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/react-menu` | `2.2.1` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/react-menubar` | `1.2.1` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/react-navigation-menu` | `1.4.1` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/react-one-time-password-field` | `0.2.1` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/react-password-toggle-field` | `0.2.1` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/react-popover` | `1.3.1` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/react-popper` | `1.4.0` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/react-portal` | `1.2.0` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/react-presence` | `1.1.11` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/react-primitive` | `2.2.0` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/react-progress` | `1.2.1` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/react-radio-group` | `1.5.1` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/react-roving-focus` | `1.2.1` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/react-scroll-area` | `1.4.0` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/react-select` | `2.4.1` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/react-separator` | `1.2.0` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/react-slider` | `1.6.1` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/react-slot` | `1.5.0` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/react-switch` | `1.4.1` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/react-tabs` | `1.2.1` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/react-toast` | `1.3.1` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/react-toggle` | `1.2.1` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/react-toggle-group` | `1.2.1` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/react-toolbar` | `1.2.1` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/react-tooltip` | `1.4.1` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/react-use-callback-ref` | `1.1.5` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/react-use-controllable-state` | `1.3.0` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/react-use-effect-event` | `0.0.5` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/react-use-escape-keydown` | `1.1.6` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/react-use-is-hydrated` | `0.1.3` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/react-use-layout-effect` | `1.1.4` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/react-use-previous` | `1.1.4` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/react-use-rect` | `1.1.4` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/react-use-size` | `1.1.5` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/react-visually-hidden` | `1.2.13` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/rect` | `1.1.3` | 전이 | `MIT` | [L03](#l03) |
| `@radix-ui/themes` | `3.3.0` | 직접 | `MIT` | [L04](#l04) |
| `aria-hidden` | `1.2.6` | 전이 | `MIT` | [L05](#l05) |
| `classnames` | `2.5.1` | 전이 | `MIT` | [L06](#l06) |
| `detect-node-es` | `1.1.0` | 전이 | `MIT` | [L07](#l07) |
| `get-nonce` | `1.0.1` | 전이 | `MIT` | [L08](#l08) |
| `lucide-react` | `0.468.0` | 직접 | `ISC` | [L09](#l09) |
| `radix-ui` | `1.8.1` | 전이 | `MIT` | [L03](#l03) |
| `react` | `19.2.0` | 직접 | `MIT` | [L10](#l10) |
| `react-dom` | `19.2.0` | 직접 | `MIT` | [L10](#l10) |
| `react-remove-scroll` | `2.7.2` | 전이 | `MIT` | [L05](#l05) |
| `react-remove-scroll-bar` | `2.3.8` | 전이 | `MIT` | [L11](#l11) |
| `react-style-singleton` | `2.2.3` | 전이 | `MIT` | [L05](#l05) |
| `scheduler` | `0.27.0` | 전이 | `MIT` | [L10](#l10) |
| `tslib` | `2.9.1` | 전이 | `0BSD` | [L12](#l12) · [L13](#l13) |
| `use-callback-ref` | `1.3.3` | 전이 | `MIT` | [L05](#l05) |
| `use-sidecar` | `1.1.3` | 전이 | `MIT` | [L05](#l05) |

## 라이선스·고지 원문

### L01

적용 패키지: `@floating-ui/core@1.8.0`, `@floating-ui/dom@1.8.0`, `@floating-ui/react-dom@2.1.9`, `@floating-ui/utils@0.2.12`

추출 위치:
- `node_modules/@floating-ui/core/LICENSE`
- `node_modules/@floating-ui/dom/LICENSE`
- `node_modules/@floating-ui/react-dom/LICENSE`
- `node_modules/@floating-ui/utils/LICENSE`

```text
MIT License

Copyright (c) 2021-present Floating UI contributors

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
the Software, and to permit persons to whom the Software is furnished to do so,
subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
```

### L02

적용 패키지: `@radix-ui/colors@3.0.0`

추출 위치:
- `node_modules/@radix-ui/colors/LICENSE`

```text
MIT License

Copyright (c) 2021 Radix

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### L03

적용 패키지: `@radix-ui/number@1.1.3`, `@radix-ui/primitive@1.2.0`, `@radix-ui/react-accessible-icon@1.2.0`, `@radix-ui/react-accordion@1.3.1`, `@radix-ui/react-alert-dialog@1.2.1`, `@radix-ui/react-arrow@1.1.17`, `@radix-ui/react-aspect-ratio@1.2.0`, `@radix-ui/react-avatar@1.3.1`, `@radix-ui/react-checkbox@1.4.1`, `@radix-ui/react-collapsible@1.2.1`, `@radix-ui/react-collection@1.2.0`, `@radix-ui/react-compose-refs@1.1.5`, `@radix-ui/react-context@1.3.0`, `@radix-ui/react-context-menu@2.4.1`, `@radix-ui/react-dialog@1.3.1`, `@radix-ui/react-direction@1.2.0`, `@radix-ui/react-dismissable-layer@1.2.1`, `@radix-ui/react-dropdown-menu@2.2.1`, `@radix-ui/react-focus-guards@1.2.0`, `@radix-ui/react-focus-scope@1.3.1`, `@radix-ui/react-form@0.3.0`, `@radix-ui/react-hover-card@1.2.1`, `@radix-ui/react-id@1.1.4`, `@radix-ui/react-label@2.1.17`, `@radix-ui/react-menu@2.2.1`, `@radix-ui/react-menubar@1.2.1`, `@radix-ui/react-navigation-menu@1.4.1`, `@radix-ui/react-one-time-password-field@0.2.1`, `@radix-ui/react-password-toggle-field@0.2.1`, `@radix-ui/react-popover@1.3.1`, `@radix-ui/react-popper@1.4.0`, `@radix-ui/react-portal@1.2.0`, `@radix-ui/react-presence@1.1.11`, `@radix-ui/react-primitive@2.2.0`, `@radix-ui/react-progress@1.2.1`, `@radix-ui/react-radio-group@1.5.1`, `@radix-ui/react-roving-focus@1.2.1`, `@radix-ui/react-scroll-area@1.4.0`, `@radix-ui/react-select@2.4.1`, `@radix-ui/react-separator@1.2.0`, `@radix-ui/react-slider@1.6.1`, `@radix-ui/react-slot@1.5.0`, `@radix-ui/react-switch@1.4.1`, `@radix-ui/react-tabs@1.2.1`, `@radix-ui/react-toast@1.3.1`, `@radix-ui/react-toggle@1.2.1`, `@radix-ui/react-toggle-group@1.2.1`, `@radix-ui/react-toolbar@1.2.1`, `@radix-ui/react-tooltip@1.4.1`, `@radix-ui/react-use-callback-ref@1.1.5`, `@radix-ui/react-use-controllable-state@1.3.0`, `@radix-ui/react-use-effect-event@0.0.5`, `@radix-ui/react-use-escape-keydown@1.1.6`, `@radix-ui/react-use-is-hydrated@0.1.3`, `@radix-ui/react-use-layout-effect@1.1.4`, `@radix-ui/react-use-previous@1.1.4`, `@radix-ui/react-use-rect@1.1.4`, `@radix-ui/react-use-size@1.1.5`, `@radix-ui/react-visually-hidden@1.2.13`, `@radix-ui/rect@1.1.3`, `radix-ui@1.8.1`

추출 위치:
- `node_modules/@radix-ui/number/LICENSE`
- `node_modules/@radix-ui/primitive/LICENSE`
- `node_modules/@radix-ui/react-accessible-icon/LICENSE`
- `node_modules/@radix-ui/react-accordion/LICENSE`
- `node_modules/@radix-ui/react-alert-dialog/LICENSE`
- `node_modules/@radix-ui/react-arrow/LICENSE`
- `node_modules/@radix-ui/react-aspect-ratio/LICENSE`
- `node_modules/@radix-ui/react-avatar/LICENSE`
- `node_modules/@radix-ui/react-checkbox/LICENSE`
- `node_modules/@radix-ui/react-collapsible/LICENSE`
- `node_modules/@radix-ui/react-collection/LICENSE`
- `node_modules/@radix-ui/react-compose-refs/LICENSE`
- `node_modules/@radix-ui/react-context/LICENSE`
- `node_modules/@radix-ui/react-context-menu/LICENSE`
- `node_modules/@radix-ui/react-dialog/LICENSE`
- `node_modules/@radix-ui/react-direction/LICENSE`
- `node_modules/@radix-ui/react-dismissable-layer/LICENSE`
- `node_modules/@radix-ui/react-dropdown-menu/LICENSE`
- `node_modules/@radix-ui/react-focus-guards/LICENSE`
- `node_modules/@radix-ui/react-focus-scope/LICENSE`
- `node_modules/@radix-ui/react-form/LICENSE`
- `node_modules/@radix-ui/react-hover-card/LICENSE`
- `node_modules/@radix-ui/react-id/LICENSE`
- `node_modules/@radix-ui/react-label/LICENSE`
- `node_modules/@radix-ui/react-menu/LICENSE`
- `node_modules/@radix-ui/react-menubar/LICENSE`
- `node_modules/@radix-ui/react-navigation-menu/LICENSE`
- `node_modules/@radix-ui/react-one-time-password-field/LICENSE`
- `node_modules/@radix-ui/react-password-toggle-field/LICENSE`
- `node_modules/@radix-ui/react-popover/LICENSE`
- `node_modules/@radix-ui/react-popper/LICENSE`
- `node_modules/@radix-ui/react-portal/LICENSE`
- `node_modules/@radix-ui/react-presence/LICENSE`
- `node_modules/@radix-ui/react-primitive/LICENSE`
- `node_modules/@radix-ui/react-progress/LICENSE`
- `node_modules/@radix-ui/react-radio-group/LICENSE`
- `node_modules/@radix-ui/react-roving-focus/LICENSE`
- `node_modules/@radix-ui/react-scroll-area/LICENSE`
- `node_modules/@radix-ui/react-select/LICENSE`
- `node_modules/@radix-ui/react-separator/LICENSE`
- `node_modules/@radix-ui/react-slider/LICENSE`
- `node_modules/@radix-ui/react-slot/LICENSE`
- `node_modules/@radix-ui/react-switch/LICENSE`
- `node_modules/@radix-ui/react-tabs/LICENSE`
- `node_modules/@radix-ui/react-toast/LICENSE`
- `node_modules/@radix-ui/react-toggle/LICENSE`
- `node_modules/@radix-ui/react-toggle-group/LICENSE`
- `node_modules/@radix-ui/react-toolbar/LICENSE`
- `node_modules/@radix-ui/react-tooltip/LICENSE`
- `node_modules/@radix-ui/react-use-callback-ref/LICENSE`
- `node_modules/@radix-ui/react-use-controllable-state/LICENSE`
- `node_modules/@radix-ui/react-use-effect-event/LICENSE`
- `node_modules/@radix-ui/react-use-escape-keydown/LICENSE`
- `node_modules/@radix-ui/react-use-is-hydrated/LICENSE`
- `node_modules/@radix-ui/react-use-layout-effect/LICENSE`
- `node_modules/@radix-ui/react-use-previous/LICENSE`
- `node_modules/@radix-ui/react-use-rect/LICENSE`
- `node_modules/@radix-ui/react-use-size/LICENSE`
- `node_modules/@radix-ui/react-visually-hidden/LICENSE`
- `node_modules/@radix-ui/rect/LICENSE`
- `node_modules/radix-ui/LICENSE`

```text
MIT License

Copyright (c) 2022 WorkOS

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### L04

적용 패키지: `@radix-ui/themes@3.3.0`

추출 위치:
- `node_modules/@radix-ui/themes/LICENSE`

```text
MIT License

Copyright (c) 2023 WorkOS

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### L05

적용 패키지: `aria-hidden@1.2.6`, `react-remove-scroll@2.7.2`, `react-style-singleton@2.2.3`, `use-callback-ref@1.3.3`, `use-sidecar@1.1.3`

추출 위치:
- `node_modules/aria-hidden/LICENSE`
- `node_modules/react-remove-scroll/LICENSE`
- `node_modules/react-style-singleton/LICENSE`
- `node_modules/use-callback-ref/LICENSE`
- `node_modules/use-sidecar/LICENSE`

```text
MIT License

Copyright (c) 2017 Anton Korzunov

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### L06

적용 패키지: `classnames@2.5.1`

추출 위치:
- `node_modules/classnames/LICENSE`

```text
The MIT License (MIT)

Copyright (c) 2018 Jed Watson

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### L07

적용 패키지: `detect-node-es@1.1.0`

추출 위치:
- `node_modules/detect-node-es/LICENSE`

```text
MIT License

Copyright (c) 2017 Ilya Kantor

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### L08

적용 패키지: `get-nonce@1.0.1`

추출 위치:
- `node_modules/get-nonce/LICENSE`

```text
MIT License

Copyright (c) 2020 Anton Korzunov

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### L09

적용 패키지: `lucide-react@0.468.0`

추출 위치:
- `node_modules/lucide-react/LICENSE`

```text
ISC License

Copyright (c) for portions of Lucide are held by Cole Bemis 2013-2022 as part of Feather (MIT). All other copyright (c) for Lucide are held by Lucide Contributors 2022.

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted, provided that the above
copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
```

### L10

적용 패키지: `react@19.2.0`, `react-dom@19.2.0`, `scheduler@0.27.0`

추출 위치:
- `node_modules/react/LICENSE`
- `node_modules/react-dom/LICENSE`
- `node_modules/scheduler/LICENSE`

```text
MIT License

Copyright (c) Meta Platforms, Inc. and affiliates.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### L11

적용 패키지: `react-remove-scroll-bar@2.3.8`

추출 위치:
- `https://raw.githubusercontent.com/theKashey/react-remove-scroll-bar/8ca9ba5ea52de03308fe8ced94f7b159a44d28ff/LICENSE`

```text
MIT License

Copyright (c) 2025 Anton Korzunov <thekashey@gmail.com>

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### L12

적용 패키지: `tslib@2.9.1`

추출 위치:
- `node_modules/tslib/CopyrightNotice.txt`

```text
/******************************************************************************
Copyright (c) Microsoft Corporation.

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY
AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT,
INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM
LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR
OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR
PERFORMANCE OF THIS SOFTWARE.
***************************************************************************** */
```

### L13

적용 패키지: `tslib@2.9.1`

추출 위치:
- `node_modules/tslib/LICENSE.txt`

```text
Copyright (c) Microsoft Corporation.

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY
AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT,
INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM
LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR
OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR
PERFORMANCE OF THIS SOFTWARE.
```
