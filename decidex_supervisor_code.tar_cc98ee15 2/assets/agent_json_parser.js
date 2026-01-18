/**
 * DecideX Agent JSON 解析工具
 * 提供容错解析功能，处理 Agent 可能输出的多种 JSON 格式
 */

/**
 * 从 Agent 响应中提取前置条件选择题 JSON
 * 支持多种格式的容错解析
 * 
 * @param {string|object} response - Agent 响应内容
 * @returns {object|null} - 解析后的 JSON 对象，解析失败返回 null
 */
function extractPreconditionQuestions(response) {
    // 情况1：直接是 JSON 对象
    if (typeof response === 'object' && response !== null) {
        if (response.type === 'precondition_questions' && Array.isArray(response.questions)) {
            return response;
        }
        // 如果是对象但没有 type 字段，可能已经解析过了
        if (Array.isArray(response.questions)) {
            return { type: 'precondition_questions', message: '请选择以下问题', questions: response.questions };
        }
        return null;
    }
    
    // 情况2：字符串类型，尝试多种解析方式
    if (typeof response === 'string') {
        const content = response.trim();
        
        // 2.1 尝试直接 JSON.parse
        try {
            const parsed = JSON.parse(content);
            if (parsed.type === 'precondition_questions' && Array.isArray(parsed.questions)) {
                return parsed;
            }
            // 如果解析成功但类型不对，返回 null
            return null;
        } catch (e) {
            // 继续尝试其他格式
        }
        
        // 2.2 尝试提取 Markdown 代码块中的 JSON (```json ... ```)
        const markdownMatch = content.match(/```json\s*([\s\S]*?)\s*```/);
        if (markdownMatch) {
            try {
                const parsed = JSON.parse(markdownMatch[1].trim());
                if (parsed.type === 'precondition_questions' && Array.isArray(parsed.questions)) {
                    return parsed;
                }
            } catch (e) {
                // 继续尝试
            }
        }
        
        // 2.3 尝试提取普通代码块中的 JSON (``` ... ```)
        const codeMatch = content.match(/```\s*([\s\S]*?)\s*```/);
        if (codeMatch) {
            try {
                const parsed = JSON.parse(codeMatch[1].trim());
                if (parsed.type === 'precondition_questions' && Array.isArray(parsed.questions)) {
                    return parsed;
                }
            } catch (e) {
                // 继续尝试
            }
        }
        
        // 2.4 尝试从文本中提取 JSON 对象（最外层的 { ... }）
        const objectMatch = content.match(/\{[\s\S]*\}/);
        if (objectMatch) {
            try {
                const parsed = JSON.parse(objectMatch[0]);
                if (parsed.type === 'precondition_questions' && Array.isArray(parsed.questions)) {
                    return parsed;
                }
            } catch (e) {
                // 继续尝试
            }
        }
        
        // 2.5 尝试提取数组（如果 Agent 直接输出了 questions 数组）
        const arrayMatch = content.match(/\[[\s\S]*\]/);
        if (arrayMatch) {
            try {
                const parsed = JSON.parse(arrayMatch[0]);
                if (Array.isArray(parsed) && parsed.length > 0 && parsed[0].question) {
                    return { type: 'precondition_questions', message: '请选择以下问题', questions: parsed };
                }
            } catch (e) {
                // 继续尝试
            }
        }
    }
    
    // 所有方式都失败，返回 null
    return null;
}

/**
 * 检测响应类型
 * 
 * @param {string|object} response - Agent 响应内容
 * @returns {string} - 响应类型：'questions' | 'analysis' | 'error'
 */
function detectResponseType(response) {
    // 尝试提取前置条件问题
    const questions = extractPreconditionQuestions(response);
    if (questions) {
        return 'questions';
    }
    
    // 检查是否包含成本分析报告的特征
    if (typeof response === 'string') {
        const content = response.toLowerCase();
        if (content.includes('成本总览') || 
            content.includes('显性成本') || 
            content.includes('决策建议')) {
            return 'analysis';
        }
    }
    
    // 其他情况视为错误或未知类型
    return 'error';
}

/**
 * 降级处理：手动输入模式
 * 当 JSON 解析失败时，让用户手动输入选择
 * 
 * @returns {object} - 手动输入模式的配置
 */
function getManualInputFallback() {
    return {
        type: 'manual_input',
        message: '系统无法自动解析问题，请手动输入你的选择：',
        manualQuestions: [
            {
                id: 1,
                question: '你的预算/成本承受能力如何？',
                options: [
                    { key: 'A', label: '非常紧张' },
                    { key: 'B', label: '适中' },
                    { key: 'C', label: '充裕' }
                ]
            },
            {
                id: 2,
                question: '你计划使用/持有多久？',
                options: [
                    { key: 'A', label: '短期（< 1年）' },
                    { key: 'B', label: '中期（1-3年）' },
                    { key: 'C', label: '长期（> 3年）' }
                ]
            },
            {
                id: 3,
                question: '你的风险承受能力如何？',
                options: [
                    { key: 'A', label: '保守' },
                    { key: 'B', label: '平衡' },
                    { key: 'C', label: '激进' }
                ]
            },
            {
                id: 4,
                question: '你最关注什么？',
                options: [
                    { key: 'A', label: '总成本最低' },
                    { key: 'B', label: '性价比最高' },
                    { key: 'C', label: '现金流压力最小' }
                ]
            }
        ]
    };
}

/**
 * 主处理函数：处理 Agent 响应
 * 
 * @param {string|object} response - Agent 响应内容
 * @returns {object} - 处理结果
 */
function handleAgentResponse(response) {
    const responseType = detectResponseType(response);
    
    if (responseType === 'questions') {
        // 成功提取前置条件问题
        const questions = extractPreconditionQuestions(response);
        return {
            success: true,
            type: 'questions',
            data: questions
        };
    } else if (responseType === 'analysis') {
        // 成本分析报告
        return {
            success: true,
            type: 'analysis',
            data: response
        };
    } else {
        // 解析失败，使用降级方案
        return {
            success: false,
            type: 'fallback',
            data: getManualInputFallback(),
            originalResponse: response
        };
    }
}

/**
 * 将用户选择转换为 Agent 可识别的格式
 * 
 * @param {Array} choices - 用户选择数组，如 ['A', 'B', 'A', 'C']
 * @returns {string} - 格式化后的字符串，如 "A、B、A、C"
 */
function formatUserChoices(choices) {
    if (!Array.isArray(choices)) {
        return '';
    }
    return choices.filter(choice => choice && choice.trim()).join('、');
}

// 导出函数（支持 CommonJS 和 ES Module）
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        extractPreconditionQuestions,
        detectResponseType,
        getManualInputFallback,
        handleAgentResponse,
        formatUserChoices
    };
}

// 示例使用
console.log('=== DecideX Agent JSON Parser ===');
console.log('函数已导出，可在前端项目中使用');
console.log('');
console.log('使用示例：');
console.log('const result = handleAgentResponse(agentResponse);');
console.log('if (result.type === "questions") {');
console.log('  renderQuestions(result.data);');
console.log('} else if (result.type === "fallback") {');
console.log('  renderManualInput(result.data);');
console.log('}');
