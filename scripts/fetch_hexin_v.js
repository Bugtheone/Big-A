/**
 * iwencai hexin-v token 生成器 (Node.js 直调)
 * 绕过 pywencai Python 封装层，直接通过 Node.js 运行 hexin-v.bundle.js
 * 用于 pywencai 库不可用时的备用方案
 */
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

function findBundleJs() {
    // 路径候选列表 (按优先级)
    const pythonVersions = ['Python313', 'Python312', 'Python311', 'Python310'];
    for (const pyVer of pythonVersions) {
        const p = path.join(process.env.APPDATA || '', 'Python', pyVer, 'site-packages', 'pywencai', 'hexin-v.bundle.js');
        if (fs.existsSync(p)) return p;
    }

    // 尝试通过 Python 定位
    try {
        const result = execSync(
            'python -c "import pywencai; import os; print(os.path.dirname(pywencai.__file__))"',
            { encoding: 'utf8', windowsHide: true, timeout: 10000 }
        );
        const bundlePath = path.join(result.trim(), 'hexin-v.bundle.js');
        if (fs.existsSync(bundlePath)) return bundlePath;
    } catch (e) { /* ignore */ }

    // 尝试 py -3
    try {
        const result = execSync(
            'py -3 -c "import pywencai; import os; print(os.path.dirname(pywencai.__file__))"',
            { encoding: 'utf8', windowsHide: true, timeout: 10000 }
        );
        const bundlePath = path.join(result.trim(), 'hexin-v.bundle.js');
        if (fs.existsSync(bundlePath)) return bundlePath;
    } catch (e) { /* ignore */ }

    return null;
}

function main() {
    const bundlePath = findBundleJs();

    if (!bundlePath) {
        console.log(JSON.stringify({
            success: false,
            error: '未找到 pywencai 的 hexin-v.bundle.js，请确认 pywencai 已安装'
        }));
        process.exit(0);
    }

    try {
        const result = execSync(
            'node "' + bundlePath + '"',
            { timeout: 15000, encoding: 'utf8', windowsHide: true }
        );
        const token = result.trim();

        if (token && token.length > 10) {
            console.log(JSON.stringify({
                success: true,
                hexin_v: token,
                cookie_string: token
            }));
        } else {
            console.log(JSON.stringify({
                success: false,
                error: '生成的 token 无效 (长度 < 10): "' + token + '"'
            }));
        }
    } catch (e) {
        console.log(JSON.stringify({
            success: false,
            error: '执行 hexin-v.bundle.js 失败: ' + e.message
        }));
    }
}

main();
