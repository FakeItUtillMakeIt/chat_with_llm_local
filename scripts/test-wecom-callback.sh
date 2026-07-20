#!/bin/bash
# 企业微信回调 URL 测试脚本

set -e

echo "测试企业微信回调 URL 是否可达"
echo ""

read -p "请输入回调 URL: " CALLBACK_URL

if [ -z "$CALLBACK_URL" ]; then
    echo "URL 不能为空"
    exit 1
fi

echo ""
echo "测试 1: GET 验证（URL 可用性）..."
GET_URL="${CALLBACK_URL}?msg_signature=test&timestamp=123&nonce=456&echostr=test_echo"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$GET_URL")
echo "  HTTP 状态码: $HTTP_CODE"

if [ "$HTTP_CODE" = "200" ]; then
    echo "  ✓ GET 验证通过"
elif [ "$HTTP_CODE" = "403" ]; then
    echo "  ⚠ 403 - 签名验证失败（正常现象，说明 URL 可达）"
else
    echo "  ✗ 请求失败，请检查 URL 或网络"
fi

echo ""
echo "测试 2: POST 模拟消息接收..."
POST_DATA='<xml><ToUserName>test</ToUserName><FromUserName>user1</FromUserName><CreateTime>1234567890</CreateTime><MsgType>text</MsgType><Content>你好</Content><MsgId>1234567890123456</MsgId></xml>'
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "Content-Type: text/xml" -d "$POST_DATA" "$CALLBACK_URL")
echo "  HTTP 状态码: $HTTP_CODE"

if [ "$HTTP_CODE" = "200" ]; then
    echo "  ✓ POST 消息接收正常"
else
    echo "  ✗ POST 请求失败"
fi

echo ""
echo "测试完成"
