#!/bin/zsh
# macapp/build-app.sh — Parrot.app 릴리스 빌드 (본인 맥 배포용, ad-hoc 서명)
set -e
cd "$(dirname "$0")"
xcodegen generate
xcodebuild -project Parrot.xcodeproj -scheme Parrot -configuration Release \
  -derivedDataPath build -destination 'platform=macOS' build
APP="build/Build/Products/Release/Parrot.app"
codesign --force --deep -s - "$APP"

# 실행 편의를 위해 dist/에 산출물 복사 (dist/는 git에 포함하지 않음 — 각자 빌드)
rm -rf dist/Parrot.app
mkdir -p dist
cp -R "$APP" dist/Parrot.app

echo "✅ 빌드 완료: $PWD/dist/Parrot.app"
echo "   open macapp/dist/Parrot.app 로 실행 (또는 /Applications로 복사)"
