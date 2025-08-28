"""
订阅多资源版本订阅插件
提供基于订阅的多资源版本管理和过滤功能
"""

import json
from typing import Dict, List, Any, Tuple, Optional
from datetime import datetime

from app.core.config import settings
from app.core.context import Context, MediaInfo, MetaInfo
from app.plugins import _PluginBase
from app.schemas.workflow import ActionContext
from app.helper.torrent import TorrentHelper
from app.helper.subscribe import SubscribeHelper
from app.helper.sites import SitesHelper
from app.modules.filter import FilterModule
from app.chain.search import SearchChain
from app.chain.download import DownloadChain
from app.helper.downloader import DownloaderHelper
from app.db.subscribe_oper import SubscribeOper
from app.db.models.subscribe import Subscribe
from app.schemas.types import MediaType
from app.utils.http import RequestUtils
from app.utils.string import StringUtils
from app.log import logger


class SubscriptionMultiVersion(_PluginBase):
    """
    订阅多资源版本订阅插件
    """

    # 插件名称
    plugin_name = "订阅多资源版本订阅"
    # 插件描述
    plugin_desc = "提供基于订阅的多资源版本管理和过滤功能"
    # 插件图标
    plugin_icon = "subscribemultiversion.png"
    # 插件版本
    plugin_version = "1.0"
    # 插件作者
    plugin_author = "Claude"
    # 作者主页
    author_url = "https://github.com/claude"
    # 插件配置项ID前缀
    plugin_config_prefix = "subscriptionmultiversion_"
    # 加载顺序
    plugin_order = 10
    # 可使用的用户级别
    auth_level = 1

    # 私有属性
    _sites_helper: SitesHelper = None
    _torrent_helper: TorrentHelper = None
    _subscribe_helper: SubscribeHelper = None
    _filter_module: FilterModule = None
    _search_chain: SearchChain = None
    _download_chain: DownloadChain = None
    _downloader_helper: DownloaderHelper = None
    _subscribe_oper: SubscribeOper = None
    _enabled: bool = False
    _enable_search: bool = True
    _enable_filter: bool = True
    _default_filter_rules: str = ""

    def init_plugin(self, config: dict = None):
        """
        初始化插件
        """
        if config:
            self._enabled = config.get("enabled")
            self._enable_search = config.get("enable_search", True)
            self._enable_filter = config.get("enable_filter", True)
            self._default_filter_rules = config.get("default_filter_rules", "")

        # 初始化助手
        self._sites_helper = SitesHelper()
        self._torrent_helper = TorrentHelper()
        self._subscribe_helper = SubscribeHelper()
        self._filter_module = FilterModule()
        self._search_chain = SearchChain()
        self._download_chain = DownloadChain()
        self._downloader_helper = DownloaderHelper()
        self._subscribe_oper = SubscribeOper()

    def get_state(self) -> bool:
        """
        获取插件状态
        """
        return self._enabled

    def get_actions(self) -> List[Dict[str, Any]]:
        """
        获取插件工作流动作
        """
        if not self._enabled:
            return []

        actions = []

        # 查询订阅种子动作
        if self._enable_search:
            actions.append({
                "id": "query_subscribe_torrents",
                "name": "查询订阅种子",
                "func": self.query_subscribe_torrents,
                "description": "根据订阅查询种子资源",
                "kwargs": {
                    "subscribe_ids": [],
                    "search_sites": []
                }
            })

        # 种子过滤动作
        if self._enable_filter:
            actions.append({
                "id": "filter_torrents",
                "name": "过滤种子",
                "func": self.filter_torrents,
                "description": "根据规则过滤种子资源",
                "kwargs": {
                    "filter_rules": self._default_filter_rules,
                    "prioritize_downloaded": True
                }
            })

        return actions

    def query_subscribe_torrents(self, context: ActionContext, **kwargs) -> Tuple[bool, ActionContext]:
        """
        查询订阅种子动作
        :param context: 工作流上下文
        :param kwargs: 动作参数
        :return: (执行状态, 更新后的上下文)
        """
        try:
            # 获取参数
            subscribe_ids = kwargs.get("subscribe_ids", [])
            search_sites = kwargs.get("search_sites", [])

            logger.info(f"开始查询订阅种子，订阅ID: {subscribe_ids}, 站点: {search_sites}")

            # 获取订阅信息
            if context.subscribes:
                # 从上下文中获取订阅
                subscribes = context.subscribes
            else:
                # 从数据库查询订阅
                if subscribe_ids:
                    subscribes = self._subscribe_oper.get_subscriptions(subscribe_ids)
                else:
                    subscribes = self._subscribe_oper.list()

            if not subscribes:
                logger.warning("未找到订阅信息")
                return True, context

            # 初始化结果
            all_torrents = []
            media_infos = []

            # 处理每个订阅
            for subscribe in subscribes:
                try:
                    # 构建媒体信息
                    media_info = MediaInfo()
                    media_info.title = subscribe.name
                    media_info.year = subscribe.year
                    media_info.type = MediaType(subscribe.type)
                    media_info.tmdb_id = subscribe.tmdbid
                    media_info.season = subscribe.season
                    media_info.episode = subscribe.episode
                    media_info.total_episode = subscribe.total_episode

                    media_infos.append(media_info)

                    # 搜索站点种子（不包含已下载种子）
                    site_torrents = self._search_site_torrents(
                        media_info,
                        search_sites,
                        subscribe
                    )
                    all_torrents.extend(site_torrents)

                except Exception as e:
                    logger.error(f"处理订阅 {subscribe.name} 时出错: {str(e)}")
                    continue

            # 更新上下文
            context.torrents = all_torrents
            context.medias = media_infos
            context.content = f"查询完成，共找到 {len(all_torrents)} 个种子资源"

            logger.info(f"查询订阅种子完成，共找到 {len(all_torrents)} 个种子")
            return True, context

        except Exception as e:
            logger.error(f"查询订阅种子失败: {str(e)}")
            return False, context

    def filter_torrents(self, context: ActionContext, **kwargs) -> Tuple[bool, ActionContext]:
        """
        过滤种子动作
        :param context: 工作流上下文
        :param kwargs: 动作参数
        :return: (执行状态, 更新后的上下文)
        """
        try:
            # 获取参数
            filter_rules = kwargs.get("filter_rules", self._default_filter_rules)
            prioritize_downloaded = kwargs.get("prioritize_downloaded", True)

            logger.info(f"开始过滤种子，规则: {filter_rules}")

            if not context.torrents and not context.subscribes:
                logger.warning("上下文中没有种子资源和订阅信息")
                return True, context

            # 解析过滤规则
            filter_params = self._parse_filter_rules(filter_rules)

            # 获取所有种子（包括已下载的种子）
            all_torrents = list(context.torrents or [])

            # 如果有订阅信息，查询已下载的种子
            if context.subscribes:
                downloaded_torrents = self._get_downloaded_torrents_from_subscribes(context.subscribes)
                # all_torrents.extend(downloaded_torrents)

            # 过滤种子
            filtered_torrents = []
            downloaded_episodes = set()  # 记录已下载的集数

            # 首先处理已下载的种子
            for torrent in downloaded_torrents:
                if torrent.meta_info and torrent.meta_info.org_string and torrent.meta_info.org_string.startswith(
                        "downloaded:"):
                    # 检查已下载种子是否通过过滤
                    if self._check_torrent_filter(torrent, filter_params):
                        # 记录已下载的集数
                        self._record_downloaded_episodes(torrent, downloaded_episodes)
                        # filtered_torrents.append(torrent)

            # 处理搜索到的种子
            for torrent in all_torrents:
                if not (torrent.meta_info and torrent.meta_info.org_string and torrent.meta_info.org_string.startswith(
                        "downloaded:")):
                    # 检查是否已经被已下载种子覆盖
                    if self._is_episode_covered(torrent, downloaded_episodes):
                        continue

                    # 应用过滤规则
                    if self._check_torrent_filter(torrent, filter_params):
                        filtered_torrents.append(torrent)

            # 更新上下文
            context.torrents = filtered_torrents
            context.content = f"过滤完成，共 {len(filtered_torrents)} 个种子通过过滤"

            # 如果有通过的种子，更新订阅状态
            if filtered_torrents and context.subscribes:
                self._update_subscribe_status(filtered_torrents, context.subscribes)

            logger.info(f"种子过滤完成，共 {len(filtered_torrents)} 个种子通过过滤")
            return True, context

        except Exception as e:
            logger.error(f"种子过滤失败: {str(e)}")
            return False, context

    def _get_downloaded_torrents_from_subscribes(self, subscribes: List[Subscribe]) -> List[Context]:
        """
        根据订阅列表获取已下载的种子
        """
        try:
            downloaded_torrents = []

            # 简化实现：从下载器获取已下载的种子
            # 由于下载器接口可能不同，这里只是一个示例实现
            try:
                # 使用DownloadChain获取下载器中的种子
                torrents = self._download_chain.get_downloading_torrents()

                for torrent in torrents:
                    # 检查种子是否匹配任何一个订阅
                    for subscribe in subscribes:
                        media_info = MediaInfo()
                        media_info.title = subscribe.name
                        media_info.year = subscribe.year
                        media_info.type = MediaType(subscribe.type)
                        media_info.tmdb_id = subscribe.tmdbid
                        media_info.season = subscribe.season
                        media_info.episode = subscribe.episode
                        media_info.total_episode = subscribe.total_episode

                        if self._match_torrent_to_subscribe(torrent, subscribe, media_info):
                            # 转换为Context对象
                            context_obj = Context()
                            context_obj.torrent_info = torrent
                            # 将下载信息存储在meta_info中
                            context_obj.meta_info = MetaInfo(title=torrent.title)
                            context_obj.meta_info.org_string = f"downloaded:unknown"
                            downloaded_torrents.append(context_obj)
                            break  # 匹配到一个订阅就停止

            except Exception as e:
                logger.error(f"获取已下载种子失败: {str(e)}")
                # 返回空列表而不是继续，避免错误传播

            logger.info(f"从下载器获取到 {len(downloaded_torrents)} 个已下载种子")
            return downloaded_torrents

        except Exception as e:
            logger.error(f"获取已下载种子失败: {str(e)}")
            return []

    def _search_site_torrents(self, media_info: MediaInfo, search_sites: List[str], subscribe: Subscribe) -> List[
        Context]:
        """
        搜索站点种子
        """
        try:
            site_torrents = []

            # 构建搜索参数
            search_params = {
                "keyword": media_info.title,
                "media_type": media_info.type.value,
                "season": media_info.season,
                "episode": media_info.episode,
                "year": media_info.year,
                "sites": search_sites if search_sites else None
            }

            # 执行搜索
            search_results = self._search_chain.search_by_title(
                search_params["keyword"],
                sites=search_params["sites"]
            )

            for result in search_results:
                try:
                    # 转换为Context对象
                    result.context = {
                        "downloaded": False,
                        "site": result.torrent_info.site_name,
                        "search_time": datetime.now().isoformat(),
                        "subscribe_id": subscribe.id
                    }
                    site_torrents.append(result)

                except Exception as e:
                    logger.error(f"处理搜索结果失败: {str(e)}")
                    continue

            logger.info(f"从站点搜索到 {len(site_torrents)} 个种子")
            return site_torrents

        except Exception as e:
            logger.error(f"搜索站点种子失败: {str(e)}")
            return []

    def _match_torrent_to_subscribe(self, torrent, subscribe: Subscribe, media_info: MediaInfo) -> bool:
        """
        检查种子是否匹配订阅
        """
        try:
            # 简单的标题匹配逻辑
            torrent_title = torrent.title.lower()
            subscribe_title = media_info.title.lower()

            # 检查标题是否包含
            if subscribe_title not in torrent_title:
                return False

            # 检查年份
            if media_info.year and str(media_info.year) not in torrent_title:
                return False

            # 检查季集信息
            if media_info.type == MediaType.TV:
                if media_info.season:
                    season_str = f"s{media_info.season:02d}"
                    if season_str not in torrent_title.lower():
                        return False

                if media_info.episode:
                    episode_str = f"e{media_info.episode:02d}"
                    if episode_str not in torrent_title.lower():
                        return False

            return True

        except Exception as e:
            logger.error(f"匹配种子到订阅失败: {str(e)}")
            return False

    def _parse_filter_rules(self, rules_str: str) -> Dict[str, Any]:
        """
        解析过滤规则
        """
        try:
            if not rules_str:
                return {}

            # 简单的JSON解析
            try:
                return json.loads(rules_str)
            except json.JSONDecodeError:
                # 如果不是JSON，尝试解析键值对
                rules = {}
                for rule in rules_str.split(","):
                    if "=" in rule:
                        key, value = rule.split("=", 1)
                        rules[key.strip()] = value.strip()
                return rules

        except Exception as e:
            logger.error(f"解析过滤规则失败: {str(e)}")
            return {}

    def _check_torrent_filter(self, torrent: Context, filter_params: Dict[str, Any]) -> bool:
        """
        检查种子是否通过过滤
        """
        try:
            # 使用MoviePilot的过滤模块
            if not filter_params:
                return True

            # 调用过滤模块
            filtered_torrents = self._filter_module.filter_torrents(
                filter_params.get("rule_groups", []),
                [torrent.torrent_info],
                torrent.media_info
            )
            return len(filtered_torrents) > 0

        except Exception as e:
            logger.error(f"检查种子过滤失败: {str(e)}")
            return False

    def _record_downloaded_episodes(self, torrent: Context, downloaded_episodes: set):
        """
        记录已下载的集数
        """
        try:
            media_info = torrent.torrent_info.media_info
            if media_info and media_info.type == MediaType.TV:
                if media_info.episode:
                    downloaded_episodes.add(media_info.episode)
                elif media_info.season:
                    # 整季下载
                    downloaded_episodes.add(f"s{media_info.season}")

        except Exception as e:
            logger.error(f"记录已下载集数失败: {str(e)}")

    def _is_episode_covered(self, torrent: Context, downloaded_episodes: set) -> bool:
        """
        检查集数是否已被覆盖
        """
        try:
            media_info = torrent.torrent_info.media_info
            if not media_info or media_info.type != MediaType.TV:
                return False

            if media_info.episode:
                return media_info.episode in downloaded_episodes
            elif media_info.season:
                return f"s{media_info.season}" in downloaded_episodes

            return False

        except Exception as e:
            logger.error(f"检查集数覆盖失败: {str(e)}")
            return False

    def _update_subscribe_status(self, filtered_torrents: List[Context], subscribes: List[Subscribe]):
        """
        更新订阅状态
        """
        try:
            # 更新订阅状态逻辑
            for torrent in filtered_torrents:
                if torrent.meta_info and torrent.meta_info.org_string and torrent.meta_info.org_string.startswith(
                        "downloaded:"):
                    # 已下载种子通过过滤，更新对应订阅状态
                    # 这里需要从org_string中解析subscribe_id，或者使用其他方式存储
                    # 由于当前实现没有存储subscribe_id，这里只是示例
                    self.post_message(
                        title="订阅状态更新",
                        text=f"已下载种子通过过滤检查"
                    )

        except Exception as e:
            logger.error(f"更新订阅状态失败: {str(e)}")

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """
        获取插件配置表单
        """
        return [
            {
                'component': 'v-switch',
                'props': {
                    'label': '启用插件',
                    'placeholder': '是否启用插件'
                },
                'name': 'enabled',
                'required': True
            },
            {
                'component': 'v-switch',
                'props': {
                    'label': '启用查询功能',
                    'placeholder': '是否启用查询订阅种子功能'
                },
                'name': 'enable_search',
                'required': True
            },
            {
                'component': 'v-switch',
                'props': {
                    'label': '启用过滤功能',
                    'placeholder': '是否启用种子过滤功能'
                },
                'name': 'enable_filter',
                'required': True
            },
            {
                'component': 'v-textarea',
                'props': {
                    'label': '默认过滤规则',
                    'placeholder': '默认的过滤规则，JSON格式或键值对格式'
                },
                'name': 'default_filter_rules',
                'required': False
            }
        ], {
            "enabled": False,
            "enable_search": True,
            "enable_filter": True,
            "default_filter_rules": ""
        }

    def get_page(self) -> List[dict]:
        """
        获取插件页面
        """
        return [
            {
                'component': 'v-form',
                'content': [
                    {
                        'component': 'v-row',
                        'content': [
                            {
                                'component': 'v-col',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'v-switch',
                                        'props': {
                                            'label': '启用插件',
                                            'model': 'enabled'
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'v-col',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'v-switch',
                                        'props': {
                                            'label': '启用查询功能',
                                            'model': 'enable_search'
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'v-row',
                        'content': [
                            {
                                'component': 'v-col',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'v-switch',
                                        'props': {
                                            'label': '启用过滤功能',
                                            'model': 'enable_filter'
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'v-row',
                        'content': [
                            {
                                'component': 'v-col',
                                'props': {
                                    'cols': 12
                                },
                                'content': [
                                    {
                                        'component': 'v-textarea',
                                        'props': {
                                            'label': '默认过滤规则',
                                            'placeholder': '默认的过滤规则，JSON格式或键值对格式',
                                            'rows': 4,
                                            'model': 'default_filter_rules'
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ]

    def stop_service(self):
        """
        停止插件服务
        """
        pass
