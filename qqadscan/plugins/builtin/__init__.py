"""内置插件包。

这些插件是「插件接口能用」的活例子，也可以直接在设置里禁用：

* :mod:`contact_signals` —— 联系方式/引流信号
* :mod:`group_context`   —— 「群号：xxxx」这类明确标注
* :mod:`obfuscation`     —— 多种伪装手法叠加

新增内置插件时，把模块名加到下面的 ``BUILTIN_PLUGIN_MODULES`` 里即可。
打包成 exe 后 ``pkgutil`` 不一定能扫到模块，所以这里用显式清单，更可靠。
"""

from __future__ import annotations

BUILTIN_PLUGIN_MODULES = (
    "contact_signals",
    "group_context",
    "obfuscation",
)
