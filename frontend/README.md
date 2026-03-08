# DecideX 前端界面

现代化的网页前端界面，用于与 DecideX 多智能体决策系统交互。

## 功能特性

- 🎨 **现代化UI设计** - 美观的深色主题界面
- 💬 **多智能体支持** - 支持切换不同的智能体（客户支持、医生预约、预订服务）
- 🎤 **语音输入** - 支持语音输入和识别
- 💾 **本地存储** - 自动保存对话记录
- 📱 **响应式设计** - 适配桌面和移动设备
- ⚡ **实时交互** - 流畅的聊天体验

## 文件结构

```
frontend/
├── index.html      # 主HTML文件
├── styles.css      # 样式文件
├── app.js          # 应用逻辑
└── README.md       # 说明文档
```

## 使用方法

### 1. 直接打开

最简单的方式是直接在浏览器中打开 `index.html` 文件：

```bash
# 在 macOS/Linux 上
open frontend/index.html

# 或使用 Python 简单服务器
cd frontend
python3 -m http.server 8000
# 然后在浏览器访问 http://localhost:8000
```

### 2. 使用本地服务器（推荐）

为了更好的体验和避免CORS问题，建议使用本地服务器：

```bash
# 使用 Python
cd frontend
python3 -m http.server 8000

# 或使用 Node.js (需要安装 http-server)
npx http-server -p 8000

# 或使用 PHP
php -S localhost:8000
```

然后在浏览器中访问 `http://localhost:8000`

### 3. 配置后端API

在 `app.js` 文件中，修改 `apiBaseUrl` 以匹配您的后端服务地址：

```javascript
apiBaseUrl: 'http://localhost:8123' // 根据实际后端地址修改
```

## 后端API接口

前端需要后端提供以下API接口：

### 1. 聊天接口

**POST** `/chat`

请求体：
```json
{
  "agent": "customer",
  "message": "用户消息",
  "conversation_id": "conv_123456"
}
```

响应：
```json
{
  "response": "智能体回复",
  "conversation_id": "conv_123456"
}
```

### 2. 语音转录接口（可选）

**POST** `/transcribe`

请求：FormData
- `audio`: 音频文件 (WAV格式)
- `agent`: 智能体类型

响应：
```json
{
  "text": "转录的文本",
  "transcription": "转录的文本"
}
```

## 功能说明

### 智能体切换

点击侧边栏中的智能体按钮可以切换不同的智能体：
- **客户支持** - 处理客户咨询和服务请求
- **医生预约** - 帮助预约和管理医生就诊
- **预订服务** - 协助进行各种预订服务

### 语音输入

1. 点击输入框左侧的麦克风图标
2. 开始说话
3. 点击"停止录音"按钮结束录音
4. 系统会自动将语音转换为文字并发送

**注意**：语音功能需要浏览器支持，并且需要用户授权麦克风权限。

### 清空对话

点击聊天区域右上角的清空按钮可以清除所有对话记录。

## 浏览器兼容性

- Chrome/Edge (推荐)
- Firefox
- Safari
- 移动浏览器

## 自定义配置

### 修改主题颜色

在 `styles.css` 文件的 `:root` 部分修改CSS变量：

```css
:root {
    --primary-color: #6366f1;
    --background: #0f172a;
    /* ... 其他颜色变量 */
}
```

### 修改智能体配置

在 `app.js` 文件的 `agents` 对象中修改智能体信息：

```javascript
const agents = {
    customer: {
        name: '客户支持智能体',
        icon: '💬',
        description: '处理客户咨询和服务请求'
    },
    // ... 添加更多智能体
};
```

## 开发建议

1. **后端集成**：确保后端API正确实现并处理CORS
2. **错误处理**：根据实际需求完善错误处理逻辑
3. **性能优化**：对于大量消息，考虑实现虚拟滚动
4. **安全性**：在生产环境中添加适当的身份验证和授权

## 故障排除

### 无法连接到后端

- 检查 `apiBaseUrl` 配置是否正确
- 确认后端服务正在运行
- 检查浏览器控制台的错误信息
- 确认CORS配置正确

### 语音功能不工作

- 检查浏览器是否支持语音识别
- 确认已授予麦克风权限
- 尝试使用HTTPS连接（某些浏览器要求）

### 消息不显示

- 检查浏览器控制台是否有错误
- 确认后端返回的数据格式正确
- 检查网络请求是否成功

## 许可证

MIT License
