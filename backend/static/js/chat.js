/** 海龟交易法则 RAG 聊天对话框 */
(function () {
    "use strict";

    const chatFab = document.getElementById("chatFab");
    const chatDialog = document.getElementById("chatDialog");
    const chatClose = document.getElementById("chatClose");
    const chatMessages = document.getElementById("chatMessages");
    const chatInput = document.getElementById("chatInput");
    const chatSend = document.getElementById("chatSend");

    let isOpen = false;
    let history = []; // [{role: "user"/"assistant", content: "..."}]
    let isSending = false;

    // ---- 打开/关闭 ----
    chatFab.addEventListener("click", toggleChat);
    chatClose.addEventListener("click", closeChat);

    function toggleChat() {
        isOpen = !isOpen;
        if (isOpen) {
            chatDialog.classList.add("open");
            chatInput.focus();
        } else {
            chatDialog.classList.remove("open");
        }
    }

    function closeChat() {
        isOpen = false;
        chatDialog.classList.remove("open");
    }

    // ---- 发送消息 ----
    chatSend.addEventListener("click", sendMessage);
    chatInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    async function sendMessage() {
        const text = chatInput.value.trim();
        if (!text || isSending) return;

        isSending = true;
        chatSend.disabled = true;
        chatInput.value = "";

        // 渲染用户消息
        appendMessage("user", text);
        // 打字指示器
        const typingId = showTyping();

        try {
            const res = await fetch("/api/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message: text, history: history }),
            });

            removeTyping(typingId);

            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || "请求失败");
            }

            const data = await res.json();
            let answerHtml = escapeHtml(data.answer);

            // 添加来源引用
            if (data.sources && data.sources.length > 0) {
                const pages = [...new Set(data.sources.map((s) => s.page))];
                answerHtml += `<span class="source-ref">—— 参考页码：${pages.join(", ")}</span>`;
            }

            appendMessage("assistant", answerHtml);

            // 更新对话历史
            history.push({ role: "user", content: text });
            history.push({ role: "assistant", content: data.answer });

            // 限制历史长度
            if (history.length > 20) history = history.slice(-20);
        } catch (e) {
            removeTyping(typingId);
            appendMessage("assistant", "抱歉，出了点问题：" + escapeHtml(e.message));
        } finally {
            isSending = false;
            chatSend.disabled = false;
            chatInput.focus();
        }
    }

    // ---- 消息渲染 ----
    function appendMessage(role, content) {
        const div = document.createElement("div");
        div.className = `message ${role}`;
        div.innerHTML = `<div class="msg-content">${content}</div>`;
        chatMessages.appendChild(div);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function showTyping() {
        const div = document.createElement("div");
        div.className = "message assistant";
        div.id = "typing-" + Date.now();
        div.innerHTML =
            '<div class="msg-content"><div class="typing-indicator"><span></span><span></span><span></span></div></div>';
        chatMessages.appendChild(div);
        chatMessages.scrollTop = chatMessages.scrollHeight;
        return div.id;
    }

    function removeTyping(id) {
        const el = document.getElementById(id);
        if (el) el.remove();
    }

    function escapeHtml(str) {
        const div = document.createElement("div");
        div.textContent = str;
        return div.innerHTML.replace(/\n/g, "<br>");
    }
})();
